import os
from pydantic import BaseModel, ValidationError
import httpx
import logging
from tqdm import tqdm

from config import template_env

from .llm_service_manager import use_inference_service

logger = logging.getLogger(__name__)


@use_inference_service
def evaluate_with_validation(
    prompt: str,
    model: BaseModel,
    max_retries: int = 3
) -> BaseModel:
    """
    Makes a request to the Llamafile server and tries up to three times to get
    a valid response.
    """
    # GBNF grammar for JSON (see https://github.com/ggerganov/llama.cpp/tree/b52b29ab9d601bb298050bcd2261169bc917ba2c/grammars)
    grammar = "root   ::= object\nvalue  ::= object | array | string | number | (\"true\" | \"false\" | \"null\") ws\n\nobject ::=\n  \"{\" ws (\n            string \":\" ws value\n    (\",\" ws string \":\" ws value)*\n  )? \"}\" ws\n\narray  ::=\n  \"[\" ws (\n            value\n    (\",\" ws value)*\n  )? \"]\" ws\n\nstring ::=\n  \"\\\"\" (\n    [^\"\\\\] |\n    \"\\\\\" ([\"\\\\/bfnrt] | \"u\" [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F] [0-9a-fA-F]) # escapes\n  )* \"\\\"\" ws\n\nnumber ::= (\"-\"? ([0-9] | [1-9] [0-9]*)) (\".\" [0-9]+)? ([eE] [-+]? [0-9]+)? ws\n\n# Optional space: by convention, applied in this grammar after literal chars when allowed\nws ::= ([ \\t\\n] ws)?"

    response = httpx.post(
        "http://localhost:7726/completion",
        json={
            "prompt": prompt,
            "grammar": grammar,
            "stop": ["<end_of_turn>"] # Gemma 2
        },
        timeout=600 # 5 minutes, same as Llamafile server
    )

    # Parse the content
    try:
        # Get the content from the response and validate it
        content = response.json()['content']
        result = model.model_validate_json(content)
    except ValidationError as e:
        # If we hit validation errors, append the invalid output and error
        # message(s) to the prompt and try again
        logger.error(f"LLM response was invalid: {content} {e}")
        prompt += f"\n\nYour output was invalid. Here is what you provided: {content}\n\nHere is the error message: {e}\n\nTry again to create a valid {model.__name__} object."
        return evaluate_with_validation(prompt, model, max_retries - 1)

    return result


def run_llamafile_completion(
    prompt: str,
    model: BaseModel,
    system_prompt: str = 'You write concise summaries of emails.'
) -> BaseModel:
    """
    Uses LlamaFile to run a completion for a given model and message.
    """
    # Render a template with the model schema
    template = template_env.get_template('core/_prompt_schema.txt')
    schema_example = template.render(schema=model.model_json_schema())

    # Take the prompt and extend it with an example of the model schema
    prompt_with_schema = f"""
    {prompt}\n\n
    {schema_example}
    """

    # Make the request to the Llamafile server
    result = evaluate_with_validation(prompt_with_schema, model)

    # Return the content
    return result


def download_file(url, output_path, chunk_size=1024*1024):
    """
    Download a file from a URL in chunks and save it to the output path.
    
    Args:
    - url (str): URL of the file to download.
    - output_path (str): Local path to save the downloaded file.
    - chunk_size (int): Size of each chunk to download. Default is 1MB.
    """
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Get the size of the file to be downloaded
    with httpx.stream("GET", url) as response:
        file_size = int(response.headers.get('content-length', 0))
        print(f"File size: {file_size / (1024 * 1024):.2f} MB")

        # Check if the file already exists and get its size
        if os.path.exists(output_path):
            downloaded_size = os.path.getsize(output_path)
            if downloaded_size >= file_size:
                print("File already downloaded.")
                return
        else:
            downloaded_size = 0

        # Download the file in chunks
        headers = {"Range": f"bytes={downloaded_size}-"}
        with httpx.stream("GET", url, headers=headers) as response:
            progress = tqdm(total=file_size, initial=downloaded_size, unit='B', unit_scale=True, desc=output_path)

            with open(output_path, "ab") as file:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    if chunk:
                        file.write(chunk)
                        progress.update(len(chunk))

            progress.close()
            logger.info(f"Downloaded {output_path}")
