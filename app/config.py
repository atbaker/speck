from celery import Celery
import os
from pydantic_settings import BaseSettings
from sqlmodel import create_engine
import sys


class Settings(BaseSettings):
    app_name: str = "Speck"

    if hasattr(sys, '_MEIPASS'):
        base_dir: str = sys._MEIPASS
        data_dir: str = os.path.join(base_dir, 'data')
    else:
        base_dir: str = os.path.dirname(os.path.abspath(__file__))
        data_dir: str = os.path.join(base_dir, 'data')

    # Database
    database_url: str = f'sqlite:///{os.path.join(data_dir, "speck.db")}'

    # Celery
    celery_dir: str = os.path.join(data_dir, 'worker')
    celery_backend_url: str = f'db+sqlite:///{os.path.join(celery_dir, "worker.db")}'
    celery_broker_dir: str = os.path.join(celery_dir, 'broker')
    celery_control_folder: str = os.path.join(celery_dir, 'control')
    celery_beat_schedule_filename: str = os.path.join(celery_dir, 'scheduler')

    # Models
    models_dir: str = os.path.join(data_dir, 'models')

settings = Settings()

engine = create_engine(settings.database_url, echo=True)

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

