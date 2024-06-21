from fastapi import APIRouter, Depends, HTTPException
import keyring
import logging
from pydantic import BaseModel

from .tasks import send_email
from .utils import get_gmail_api_client

logger = logging.getLogger(__name__)

router = APIRouter()


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
