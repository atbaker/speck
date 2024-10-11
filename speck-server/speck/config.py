from diskcache import Cache
import os
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
import platform
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
import sqlite_vec
import sys


# Determine our base directory based on whether we're packaged in PyInstaller or not
if hasattr(sys, '_MEIPASS'):
    PACKAGED: bool = True
    BASE_DIR: str = sys._MEIPASS
else:
    PACKAGED: bool = False
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))


class Settings(BaseSettings):
    app_name: str = 'Speck' if PACKAGED else 'Speck (dev)'
    os_name: str = platform.system()
    packaged: bool = PACKAGED

    app_data_dir: str = os.environ.get('APP_DATA_DIR', os.path.dirname(BASE_DIR))
    speck_data_dir: str = os.path.join(app_data_dir, 'data')

    # Logging
    log_dir: str = os.path.join(app_data_dir, 'logs')

    # Database
    database_path: str = os.path.join(speck_data_dir, "speck.db")
    database_url: str = f'sqlite:///{database_path}'

    # Cache
    cache_dir: str = os.path.join(speck_data_dir, 'cache')

    # Task manager
    task_manager_log_file: str = os.path.join(log_dir, 'worker.log') if PACKAGED else ''
    recurring_tasks: list[tuple[str, int, tuple, dict]] = [
        ('emails.tasks.sync_inbox', 60, (), {})  # (task, interval in seconds, args, kwargs)
    ]

    # Playwright
    playwright_browsers_dir: str = os.path.join(speck_data_dir, 'browsers')
    os.makedirs(playwright_browsers_dir, exist_ok=True)
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = playwright_browsers_dir

    # Local model server
    models_dir: str = os.path.join(speck_data_dir, 'models')

    llamafile_exe_path: str = os.path.join(BASE_DIR, 'llamafile')
    llamafiler_exe_path: str = os.path.join(BASE_DIR, 'llamafiler')
    # Append a ".exe" extension if on Windows
    if os_name == 'Windows':
        llamafile_exe_path += '.exe'
        llamafiler_exe_path += '.exe'

    # Cloud vs. local completion
    use_local_completions: bool = False

    # Cloud inference
    cloud_inference_providers: dict = {
        # 'cudo': {
        #     'endpoint': 'https://crom.myspeck.ai/v1',
        #     'api_key': os.environ['VLLM_API_KEY'],
        #     'model': 'hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4'
        # },
        'cerebras': {
            'endpoint': 'https://api.cerebras.ai/v1',
            'api_key': os.environ['CEREBRAS_API_KEY'],
            'model': 'llama3.1-70b'
        },
        'fireworks': {
            'endpoint': 'https://api.fireworks.ai/inference/v1',
            'api_key': os.environ['FIREWORKS_API_KEY'],
            'model': 'accounts/fireworks/models/llama-v3p1-70b-instruct'
        }
    }

    # Google OAuth
    gcp_client_id: str = '967796201989-uuj3ieb0dpijshemdt33umac2vl2o914.apps.googleusercontent.com'
    gcp_client_secret: str = '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'
    gcp_auth_uri: str = 'https://accounts.google.com/o/oauth2/auth'
    gcp_redirect_uri: str = 'https://www.myspeck.ai/redirect-to-app'
    gcp_token_uri: str = 'https://oauth2.googleapis.com/token'
    gcp_oauth_scopes: list = [
        'https://www.googleapis.com/auth/gmail.modify'
    ]

settings = Settings()

# Make sure the data and log directories exist
os.makedirs(settings.speck_data_dir, exist_ok=True)
os.makedirs(settings.log_dir, exist_ok=True)

# SQLModel
db_engine = create_engine(settings.database_url)

def get_db_session():
    with Session(db_engine) as session:
        yield session

# Enable sqlite-vec for embedding storage
@event.listens_for(db_engine, 'connect')
def on_connect(connection, _):
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)

# Diskcache
cache = Cache(directory=settings.cache_dir)

# Jinja2
template_env = Environment(
    loader=ChoiceLoader([
        FileSystemLoader(os.path.join(BASE_DIR, 'core', 'templates')),
        FileSystemLoader(os.path.join(BASE_DIR, 'emails', 'templates')),
        FileSystemLoader(os.path.join(BASE_DIR, 'profiles', 'templates')),
    ]),
    autoescape=select_autoescape(),
)
