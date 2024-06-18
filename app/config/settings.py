import os
from pydantic_settings import BaseSettings
import sys


class Settings(BaseSettings):
    app_name: str = "Speck"

    if hasattr(sys, '_MEIPASS'):
        base_dir: str = sys._MEIPASS
    else:
        config_dir: str = os.path.dirname(os.path.abspath(__file__))
        base_dir: str = os.path.dirname(config_dir)

    # Database
    database_url: str = f'sqlite:///{os.path.join(base_dir, "speck.db")}'

    # Huey
    huey_database_file: str = f'{os.path.join(base_dir, "huey.db")}'

settings = Settings()
