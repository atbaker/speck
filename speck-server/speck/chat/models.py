from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models import Base
from emails.models import Mailbox


class Message(BaseModel):
    author: Literal['user', 'assistant']
    content: str
    created_at: datetime = Field(default_factory=datetime.now)


class Conversation(Base):
    __tablename__ = 'conversations'

    id: Mapped[int] = mapped_column(primary_key=True)

    mailbox_id: Mapped[int] = mapped_column(ForeignKey('mailboxes.id'))
    mailbox: Mapped["Mailbox"] = relationship()

    messages: Mapped[list[Message]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

