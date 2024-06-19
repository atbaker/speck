import os
from pydantic_settings import BaseSettings
import sys


class Settings(BaseSettings):
    app_name: str = "Speck"

    if hasattr(sys, '_MEIPASS'):
        base_dir: str = sys._MEIPASS
        data_dir: str = os.path.join(base_dir, 'data')
    else:
        config_dir: str = os.path.dirname(os.path.abspath(__file__))
        base_dir: str = os.path.dirname(config_dir)
        data_dir: str = os.path.join(base_dir, 'data')

    # Database
    database_url: str = f'sqlite:///{os.path.join(base_dir, "speck.db")}'

    # Celery
    celery_dir: str = os.path.join(data_dir, 'worker')
    celery_backend_url: str = f'db+sqlite:///{os.path.join(celery_dir, "worker.db")}'
    celery_broker_dir: str = os.path.join(celery_dir, 'broker')
    celery_control_folder: str = os.path.join(celery_dir, 'control')
    celery_beat_schedule_filename: str = os.path.join(celery_dir, 'scheduler')

settings = Settings()
