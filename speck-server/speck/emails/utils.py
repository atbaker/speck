import googleapiclient.discovery
import google.oauth2.credentials
import keyring

from config import settings


def _get_user_credentials():
    """Get the stored user credentials from the keyring library."""
    access_token = keyring.get_password(settings.app_name, 'google_oauth_access_token')
    refresh_token = keyring.get_password(settings.app_name, 'google_oauth_refresh_token')

    if access_token is None or refresh_token is None:
        raise Exception("No stored credentials found.")

    return google.oauth2.credentials.Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=settings.gcp_token_uri,
        client_id=settings.gcp_client_id,
        client_secret=settings.gcp_client_secret,
        scopes=settings.gcp_oauth_scopes,
    )


def get_gmail_api_client():
    """
    Get the Gmail API client and make one API request to
    refresh the access token.
    """
    credentials = _get_user_credentials()
    client = googleapiclient.discovery.build('gmail', 'v1', credentials=credentials, cache_discovery=False)

    # Make a request to refresh the access token
    client.users().getProfile(userId='me').execute()

    # Store our refreshed access token in the keyring
    keyring.set_password(settings.app_name, 'google_oauth_access_token', credentials.token)

    return client
