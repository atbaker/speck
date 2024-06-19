from celery import Celery
from sqlmodel import create_engine

from .settings import settings

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
    imports=['emails.tasks'],
)
