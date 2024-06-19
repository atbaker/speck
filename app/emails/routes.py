from fastapi import APIRouter, Depends, HTTPException
import keyring
from llama_cpp import Llama
import logging
from pydantic import BaseModel

from .tasks import send_email
from .utils import get_gmail_api_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/load-model')
async def load_model():
    logger.info("Loading Llama model...")
    state.llm = Llama.from_pretrained(
        repo_id='QuantFactory/Meta-Llama-3-8B-Instruct-GGUF',
        filename='Meta-Llama-3-8B-Instruct.Q4_0.gguf',
        local_dir=BASE_DIR + '/models',
        n_gpu_layers=-1,
    )
    logger.info("Llama model loaded.")
    return {"status": "success"}


@router.get('/chat')
async def chat(prompt: str):
    if state.llm is None:
        raise HTTPException(status_code=400, detail="Model not loaded. Please load the model first.")

    logger.info('Starting inference...')
    output = state.llm(
        prompt, # Prompt
        max_tokens=128, # Generate up to 128 tokens, set to None to generate up to the end of the context window
        stop=["Q:", "\n"], # Stop generating just before the model would generate a new question
        echo=True # Echo the prompt back in the output
    )
    logger.info('Inference complete.')
    return {"output": output['choices'][0]['text']}


class TokenData(BaseModel):
    access_token: str
    refresh_token: str


@router.post('/store-oauth-tokens')
async def store_oauth_tokens(token_data: TokenData):
    """A simple endpoint to store the OAuth tokens using the keyring library."""
    keyring.set_password('Speck', 'google_oauth_access_token', token_data.access_token)
    keyring.set_password('Speck', 'google_oauth_refresh_token', token_data.refresh_token)
    return {"status": "success"}


@router.get('/test-send-email')
async def test_send_email():
    send_email.delay()
    return {"status": "success"}
