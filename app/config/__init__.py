from huey import SqliteHuey
from sqlmodel import create_engine

from .settings import settings

engine = create_engine(settings.database_url, echo=True)

huey = SqliteHuey(filename=settings.huey_database_file)
