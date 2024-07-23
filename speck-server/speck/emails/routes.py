import base64
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
import hashlib
import httpx
import keyring
import logging
from pydantic import BaseModel
from urllib.parse import urlencode
import secrets
from sqlalchemy.exc import NoResultFound
from sqlmodel import select, Session

from config import settings, get_db_session

from .models import Mailbox, Message
from .utils import get_gmail_api_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/start-google-oauth')
async def start_oauth():
    # Generate a code_verifier and store it with keyring
    code_verifier = secrets.token_urlsafe(128)
    keyring.set_password(settings.app_name, 'google_oauth_code_verifier', code_verifier)

    # Hash and encode the code_verifier into a code_challenge
    hashed_verifier = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(hashed_verifier).decode().rstrip('=')

    query_params = {
        "response_type": "code",
        "client_id": settings.gcp_client_id,
        "redirect_uri": settings.gcp_redirect_uri,
        "scope": ','.join(settings.gcp_oauth_scopes),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent"
    }

    auth_url = f"{settings.gcp_auth_uri}?{urlencode(query_params)}"

    return RedirectResponse(auth_url)


class OAuthCodeData(BaseModel):
    code: str


@router.post('/receive-oauth-code')
async def receive_oauth_code(*, session: Session = Depends(get_db_session), codeData: OAuthCodeData):
    oauth_code = codeData.code

    # Exchange the code for access and refresh tokens
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'https://oauth2.googleapis.com/token',
            data={
                'client_id': settings.gcp_client_id,
                'client_secret': settings.gcp_client_secret, # Annoying necessary, see https://stackoverflow.com/questions/76528208/google-oauth-2-0-authorization-code-with-pkce-requires-a-client-secret
                'redirect_uri': settings.gcp_redirect_uri,
                'grant_type': 'authorization_code',
                'code': oauth_code,
                'code_verifier': keyring.get_password(settings.app_name, 'google_oauth_code_verifier'),
            }
        )

        token_data = response.json()

    # Store the tokens with keyring
    keyring.set_password(settings.app_name, 'google_oauth_access_token', token_data['access_token'])
    keyring.set_password(settings.app_name, 'google_oauth_refresh_token', token_data['refresh_token'])

    # And remove our code_verifier
    keyring.delete_password(settings.app_name, 'google_oauth_code_verifier')

    # Finally, fetch the user's profile info and get or create their Mailbox
    client = get_gmail_api_client()
    user_profile = client.users().getProfile(userId='me').execute()
    email_address = user_profile['emailAddress']

    try:
        mailbox = session.exec(
            select(Mailbox).where(Mailbox.email_address == email_address)
        ).one()
    except NoResultFound:
        mailbox = Mailbox(email_address=email_address)
        session.add(mailbox)
        session.commit()

    return {"status": "success", "access_token": token_data['access_token'], "refresh_token": token_data['refresh_token']}


@router.get('/test-sync-inbox')
async def test_sync_inbox(*, session: Session = Depends(get_db_session)):
    mailbox = session.exec(select(Mailbox)).one()
    mailbox.sync_inbox(session=session)
    return {"status": "success"}


@router.get('/summary')
async def get_summary(threadId: str, session: Session = Depends(get_db_session)):
    """Retrieves the summary of a specific thread."""
    try:
        message = session.exec(select(Message).where(Message.thread_id == threadId)).one()
    except NoResultFound:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "success", "summary": message.summary}
