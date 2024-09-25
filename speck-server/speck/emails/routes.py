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
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound
# from sqlmodel import select, Session

from config import settings, get_db_session
from core.task_manager import task_manager
from profiles.models import Profile

from .models import Mailbox
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

    # Finally, fetch the user's profile info and get or create their Mailbox and Profile
    client = get_gmail_api_client()
    user_profile = client.users().getProfile(userId='me').execute()
    email_address = user_profile['emailAddress']

    try:
        mailbox = session.execute(
            select(Mailbox).where(Mailbox.email_address == email_address)
        ).scalar_one()
    except NoResultFound:
        mailbox = Mailbox(email_address=email_address)
        session.add(mailbox)
        session.commit() # Commit first to get the mailbox id

        # profile = Profile(mailbox_id=mailbox.id)
        # session.add(profile)
        session.commit()

    # Kick off an initial sync of the mailbox
    from .tasks import sync_inbox
    task_manager.add_task(task=sync_inbox)

    return {"status": "success"}
