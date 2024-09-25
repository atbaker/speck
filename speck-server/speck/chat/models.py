from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy.dialects.sqlite import JSON
from sqlmodel import Column, Field as SQLModelField, SQLModel, Relationship

from emails.models import Mailbox


class Message(BaseModel):
    author: Literal['user', 'assistant']
    content: str
    created_at: datetime = Field(default_factory=datetime.now)


class Conversation(SQLModel, table=True):
    id: int | None = SQLModelField(default=None, primary_key=True)

    mailbox_id: int = SQLModelField(default=None, foreign_key='mailbox.id')
    # mailbox: "Mailbox" = Relationship(back_populates='conversations')

    messages: list[Message] = SQLModelField(sa_column=Column(JSON))

    created_at: datetime = SQLModelField(default_factory=datetime.now)

