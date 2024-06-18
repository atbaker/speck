import googleapiclient.discovery
import google.oauth2.credentials
import keyring


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
