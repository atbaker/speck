from datetime import datetime
from sqlmodel import Field, SQLModel


class Email(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    snippet: str
    received_at: datetime
    body: str
    created_at: datetime = Field(default_factory=datetime.now)
