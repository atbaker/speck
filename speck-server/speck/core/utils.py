import logging
import os
from typing import Dict

import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, delete, text

from config import db_engine, settings

from .llm_service_manager import use_local_inference_service

logger = logging.getLogger(__name__)


@use_local_inference_service(model_type='embedding')
def generate_embedding(content: str):
    """
    Generate a serialized binary embedding for a given string using Llamafiler.
    """
    data = {
        'content': content
    }
    response = httpx.post("http://127.0.0.1:17726/embedding", json=data)

    embedding = response.json()['embedding']

    return embedding

@use_local_inference_service(model_type='completion')
def generate_completion_with_validation(
        prompt_template: str,
        partial_variables: Dict,
        input_variables: Dict,
        output_model: BaseModel,
        llm_temperature: float = 0.2,
        max_retries: int = 3
):
    """
    Uses LangChain and RunPod to evaluate a prompt and return a Pydantic
    model.
    """
    from langchain_core.output_parsers import PydanticOutputParser
    parser = PydanticOutputParser(pydantic_object=output_model)

    # Extend the prompt with the output format, and add format instructions to our partial variables
    prompt_template += "\n<output-format>Wrap the output in triple backticks (```), not <json> tags.\n{{format_instructions}}</output-format>"
    partial_variables['format_instructions'] = parser.get_format_instructions()

    # Render the prompt with the partial variables
    prompt = ChatPromptTemplate.from_template(
        template=prompt_template,
        template_format='jinja2',
        partial_variables=partial_variables
    )

    # Set our base_url for local or cloud completions
    if settings.use_local_completions:
        base_url = 'http://127.0.0.1:17727/v1'
        api_key = 'not-necessary-for-local-completions'
        model = ''
    else:
        provider_settings = settings.cloud_inference_providers['cerebras']
        base_url = provider_settings['endpoint']
        api_key = provider_settings['api_key']
        model = provider_settings['model']

    llm = ChatOpenAI(
        base_url=base_url,
        openai_api_key=api_key,
        model=model,
        temperature=llm_temperature
    )

    chain = prompt | llm | parser

    try:
        result = chain.invoke(input=input_variables)
    except OutputParserException as parsing_error:
        # If we've exhausted all our retries, just re-raise the exception
        if max_retries <= 0:
            raise parsing_error

        # Otherwise, include the error message in the prompt and try again
        logger.error(f"LLM response was invalid: {parsing_error}")
        prompt_template += f"\n\n<output-parsing-error>Your output was invalid. Here is what you provided: {parsing_error.llm_output}\n\nHere is the error message: {parsing_error}\n\nTry again to create a valid {output_model.__name__} object.</output-parsing-error>"
        result = generate_completion_with_validation(
            prompt_template,
            partial_variables,
            input_variables,
            output_model,
            llm_temperature=llm_temperature,
            max_retries=max_retries - 1
        )

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


def create_database_tables():
    """
    Sets up the database using SQLModel and sqlite-vec.
    """
    # Create the vec_messages table first if it doesn't exist
    with Session(db_engine) as session:
        session.execute(
            text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_message using vec0 (
                    message_id TEXT PRIMARY KEY,
                    body_embedding FLOAT[1024]
                )
                """)
        )

    # Create the database tables
    from core.models import Base
    from emails import models as email_models
    from chat import models as chat_models
    # from profiles import models as profile_models
    Base.metadata.create_all(db_engine)

def reset_database():
    """
    Resets the Speck database. Used during local development.
    """
    from emails.models import Mailbox, Message, VecMessage, Thread
    with Session(db_engine) as session:
        # Keep the Mailbox but reset the sync fields
        mailboxes = session.exec(select(Mailbox)).all()
        for mailbox in mailboxes:
            mailbox.last_history_id = None
            mailbox.last_synced_at = None
            session.add(mailbox)

        # Delete all VecMessage, Message, and Thread rows
        session.exec(delete(VecMessage))
        session.exec(delete(Message))
        session.exec(delete(Thread))

        # The LangGraph SQLite checkpointer creates additional tables we need
        # to delete manually
        session.exec(text("DROP TABLE IF EXISTS writes"))
        session.exec(text("DROP TABLE IF EXISTS checkpoints"))

        session.commit()
