import json
import os
from pydantic import BaseModel, ValidationError
import httpx
import logging

from config import template_env

from .llm_service_manager import use_inference_service
from .pydantic_models_to_gbnf_grammar import generate_gbnf_grammar_and_documentation

logger = logging.getLogger(__name__)


@use_inference_service
def evaluate_with_validation(
    prompt: str,
    grammar: str,
    model: BaseModel,
    max_retries: int = 3
) -> BaseModel:
    """
    Makes a request to the Llamafile server and tries up to three times to get
    a valid response.
    """
    data = {
        "prompt": prompt,
        "cache_prompt": True,
        "grammar": grammar,
        "temperature": 0.2,
        "stream": True,
        "stop": ["<eos>", "<end_of_turn>"], # Gemma 2 TODO - Not sure if <eos> is necessary here...
        # "stop": ["<|endoftext|>"], # Phi 3
    }

    # Stream the response, so we can abort and retry quickly if the LLM gets stuck
    content = ''
    with httpx.stream('POST', "http://localhost:17726/completion", json=data, timeout=180) as response:
        for text in response.iter_text():
            try:
                data = json.loads(
                    text.strip('data :') # Strip out "data :" prefix
                )
                content += data['content']
                logger.debug(f"LLM partial response: {content}")
                print(f"LLM partial response: {content}")
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON: {text}")
                raise

    try:
        # Validate the response
        result = model.model_validate_json(content)
    except ValidationError as e:
        # If we've exhausted all our retries, just re-raise the exception
        if max_retries <= 0:
            raise

        # If we hit validation errors, append the invalid output and error
        # message(s) to the prompt and try again
        logger.error(f"LLM response was invalid: {content} {e}")
        prompt += f"\n\nYour output was invalid. Here is what you provided: {content}\n\nHere is the error message: {e}\n\nTry again to create a valid {model.__name__} object."
        return evaluate_with_validation(
            prompt,
            grammar,
            model,
            max_retries - 1
        )

    return result


def run_llamafile_completion(
    prompt: str,
    model: BaseModel,
    system_prompt: str = 'You write concise summaries of emails.'
) -> BaseModel:
    """
    Uses LlamaFile to run a completion for a given model and message.
    """
    # Generate the GBNF grammar and documentation
    grammar, documentation = generate_gbnf_grammar_and_documentation(
        pydantic_model_list=[model]
    )

    # Render a template with the model schema
    template = template_env.get_template('_response_format.txt')
    response_format = template.render(
        model_docs=documentation,
    )

    # Take the prompt and extend it with an example of the model schema
    prompt_with_schema = f"""
    {prompt}\n\n
    {response_format}
    """

    # Make the request to the Llamafile server
    result = evaluate_with_validation(
        prompt_with_schema,
        grammar,
        model
    )

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
    with httpx.stream("GET", url, follow_redirects=True) as response:
        file_size = int(response.headers.get('content-length', 0))
        logger.info(f"File size: {file_size / (1024 * 1024):.2f} MB")

        # Check if the file already exists and get its size
        if os.path.exists(output_path):
            downloaded_size = os.path.getsize(output_path)
            if downloaded_size >= file_size:
                logger.info("File already downloaded.")
                return
        else:
            downloaded_size = 0

        # Download the file in chunks
        headers = {"Range": f"bytes={downloaded_size}-"}
        with httpx.stream("GET", url, headers=headers, follow_redirects=True) as response:
            with open(output_path, "ab") as file:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    if chunk:
                        file.write(chunk)
                        downloaded_size += len(chunk)
                        logger.info(f"Downloaded {downloaded_size / (1024 * 1024):.2f} MB of {file_size / (1024 * 1024):.2f} MB")

            logger.info(f"Downloaded {output_path}")
