import logging
import os
from typing import Dict

import httpx
from langchain_core.prompts import ChatPromptTemplate
from langchain_fireworks import ChatFireworks
from pydantic import BaseModel
from sqlite_vec import serialize_float32
from sqlmodel import SQLModel, Session, select, text

from config import db_engine, settings

from .llm_service_manager import use_inference_service

logger = logging.getLogger(__name__)


@use_inference_service(model_type='embedding')
def generate_embedding(content: str):
    """
    Generate a serialized binary embedding for a given string using Llamafile.
    """
    data = {
        'content': content
    }
    response = httpx.post("http://localhost:17726/embedding", json=data)

    embedding = response.json()['embedding']

    return embedding


def generate_completion_with_validation(
        prompt_template: str,
        partial_variables: Dict,
        input_variables: Dict,
        output_model: BaseModel,
        llm_temperature: float = 0.2,
        max_retries: int = 3
):
    """
    Uses LangChain and Fireworks to evaluate a prompt and return a Pydantic
    model.
    """
    prompt = ChatPromptTemplate.from_template(
        template=prompt_template,
        template_format='jinja2',
        partial_variables=partial_variables
    )

    llm = ChatFireworks(
        model=settings.fireworks_default_model,
        temperature=llm_temperature
    ).with_structured_output(output_model, include_raw=True)

    chain = prompt | llm

    result = chain.invoke(input=input_variables)

    # If we got a parsed result on the first try, return it
    if result['parsed']:
        return result['parsed']

    # Otherwise, we got a parsing error
    parsing_error = result['parsing_error']

    # If we've exhausted all our retries, just re-raise the exception
    if max_retries <= 0:
        raise parsing_error

    # Extract the bad arguments from the raw result's function call
    # TODO: Might need to account for multiple tool calls in the future?
    bad_arguments = result['raw'].additional_kwargs['tool_calls'][0]['function']['arguments']

    # Otherwise, include the error message in the prompt and try again
    logger.error(f"LLM response was invalid: {bad_arguments} {parsing_error}")
    prompt_template += f"\n\nYour output was invalid. Here is what you provided: {bad_arguments}\n\nHere is the error message: {parsing_error}\n\nTry again to create a valid {output_model.__name__} object."
    return generate_completion_with_validation_langchain(
        prompt_template,
        partial_variables,
        input_variables,
        output_model,
        llm_temperature=llm_temperature,
        max_retries=max_retries - 1
    )

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
        session.exec(
            text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_message using vec0 (
                    message_id TEXT PRIMARY KEY,
                    body_embedding FLOAT[1024]
                )
                """)
        )

    # Create the database tables
    from emails import models as email_models
    from profiles import models as profile_models
    SQLModel.metadata.create_all(db_engine)

def reset_database():
    """
    Resets the Speck database. Used during local development.
    """
    # Delete all Message and VecMessage rows
    from emails.models import Message, VecMessage, Thread
    with Session(db_engine) as session:
        statement = select(Message)
        messages = session.exec(statement).all()
        for message in messages:
            session.delete(message)

        statement = select(VecMessage)
        vec_messages = session.exec(statement).all()
        for vec_message in vec_messages:
            session.delete(vec_message)

        statement = select(Thread)
        threads = session.exec(statement).all()
        for thread in threads:
            session.delete(thread)

        session.commit()
