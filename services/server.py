from fastapi import FastAPI, Depends, HTTPException
import googleapiclient.discovery
import google.oauth2.credentials
import keyring
from llama_cpp import Llama
import logging
import os
from pydantic import BaseModel


logger = logging.getLogger(__name__)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class AppState:
    def __init__(self):
        self.llm = None


app = FastAPI()
state = AppState()


@app.get("/")
async def hello_world():
    return {"output": "Hello, world!"}


@app.get('/load-model')
async def load_model(state: AppState = Depends(lambda: state)):
    logger.info("Loading Llama model...")
    state.llm = Llama.from_pretrained(
        repo_id='QuantFactory/Meta-Llama-3-8B-Instruct-GGUF',
        filename='Meta-Llama-3-8B-Instruct.Q4_0.gguf',
        local_dir=BASE_DIR + '/models',
        n_gpu_layers=-1,
    )
    logger.info("Llama model loaded.")
    return {"status": "success"}


@app.get('/chat')
async def chat(prompt: str, state: AppState = Depends(lambda: state)):
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


def _get_user_credentials():
    """Get the stored user credentials from the keyring library."""
    access_token = keyring.get_password('Speck', 'google_oauth_access_token')
    refresh_token = keyring.get_password('Speck', 'google_oauth_refresh_token')

    if access_token is None or refresh_token is None:
        raise Exception("No stored credentials found.")

    return google.oauth2.credentials.Credentials(
        token=access_token,
    )


def get_gmail_api_client():
    """Get the Gmail API client."""
    credentials = _get_user_credentials()
    return googleapiclient.discovery.build('gmail', 'v1', credentials=credentials)


@app.post('/store-oauth-tokens')
async def store_oauth_tokens(token_data: TokenData):
    """A simple endpoint to store the OAuth tokens using the keyring library."""
    keyring.set_password('Speck', 'google_oauth_access_token', token_data.access_token)
    keyring.set_password('Speck', 'google_oauth_refresh_token', token_data.refresh_token)
    return {"status": "success"}


if __name__ == "__main__":
    # Start the server
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7725)
