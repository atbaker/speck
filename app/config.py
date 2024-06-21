from celery import Celery
import os
from diskcache import Cache
import platform
from pydantic_settings import BaseSettings
from sqlmodel import create_engine
import sys


class Settings(BaseSettings):
    app_name: str = "Speck"
    os_name: str = platform.system()

    # Determine whether we're packaged in PyInstaller or not
    if hasattr(sys, '_MEIPASS'):
        base_dir: str = sys._MEIPASS
        data_dir: str = os.path.join(base_dir, 'data')
    else:
        base_dir: str = os.path.dirname(os.path.abspath(__file__))
        data_dir: str = os.path.join(base_dir, 'data')

    # Logging
    log_dir: str = os.path.join(data_dir, 'logs')

    # Database
    database_url: str = f'sqlite:///{os.path.join(data_dir, "speck.db")}'

    # Cache
    cache_dir: str = os.path.join(data_dir, 'cache')

    # Celery
    celery_dir: str = os.path.join(data_dir, 'worker')
    celery_backend_url: str = f'db+sqlite:///{os.path.join(celery_dir, "worker.db")}'
    celery_broker_dir: str = os.path.join(celery_dir, 'broker')
    celery_control_folder: str = os.path.join(celery_dir, 'control')
    celery_beat_schedule_filename: str = os.path.join(celery_dir, 'scheduler')

    # LLM server
    llm_server_state_path: str = os.path.join(data_dir, 'llm_server_state.json')
    models_dir: str = os.path.join(data_dir, 'models')

    llamafile_exe_path: str = os.path.join(data_dir, 'llamafile')
    # Append a ".exe" extension if on Windows
    if os_name == 'Windows':
        llamafile_exe_path += '.exe'

    # Google OAuth
    gcp_client_id: str = '967796201989-uuj3ieb0dpijshemdt33umac2vl2o914.apps.googleusercontent.com'
    gcp_client_secret: str = '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'
    gcp_auth_uri: str = 'https://accounts.google.com/o/oauth2/auth'
    gcp_redirect_uri: str = 'https://atbaker.ngrok.io/receive-oauth-code'
    gcp_token_uri: str = 'https://oauth2.googleapis.com/token'
    gcp_oauth_scopes: list = [
    'https://www.googleapis.com/auth/gmail.readonly',
]

settings = Settings()
os.makedirs(settings.log_dir, exist_ok=True)

engine = create_engine(settings.database_url, echo=True)

cache = Cache(directory=settings.cache_dir)

celery_app = Celery(
    'app',
    backend=settings.celery_backend_url,
    beat_schedule_filename=settings.celery_beat_schedule_filename,
    broker_url='filesystem://',
    broker_transport_options={
        'data_folder_in': settings.celery_broker_dir,
        'data_folder_out': settings.celery_broker_dir,
        'control_folder': settings.celery_control_folder,
    },
    imports=['emails.tasks', 'setup.tasks'],
)

