from datetime import datetime
from pydantic import BaseModel
from typing import Literal
import uuid
from langgraph.checkpoint.sqlite import SqliteSaver

import pendulum

from sqlalchemy import ForeignKey, UUID
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import settings
from chat.graph import get_graph_builder
from core.models import Base
from emails.models import Mailbox


class Message(BaseModel):
    """A message in a Conversation."""
    id: str
    sender: Literal['user', 'speck']
    content: str
    created_at: datetime


class Conversation(Base):
    __tablename__ = 'conversations'

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)

    mailbox_id: Mapped[int] = mapped_column(ForeignKey('mailboxes.id'))
    mailbox: Mapped["Mailbox"] = relationship()

    messages: Mapped[list[Message]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    def process_user_message(self, contents: str):
        """Process a new message by adding it to the conversation and invoking the graph."""
        # Note the time for the user's message
        user_message_created_at = pendulum.now()

        # Set the thread_id to this conversation's id
        config = {"configurable": {"thread_id": self.id}}

        # Compile the graph and invoke it using the SQLite checkpointer
        with SqliteSaver.from_conn_string(settings.database_path) as sqlite_checkpointer:
            graph_builder = get_graph_builder()
            graph = graph_builder.compile(checkpointer=sqlite_checkpointer)
            response = graph.invoke({"messages": [("user", contents)]}, config)

        # Add the new messages to the conversation
        conversation_message_ids = [message.id for message in self.messages]
        for graph_message in response["messages"]:
            # If this message is already in the conversation, skip it
            if graph_message.id in conversation_message_ids:
                continue

            # Ignore any messages which aren't intended for the user to see
            message_type = graph_message.type
            if message_type not in ('human', 'ai'):
                continue

            message = Message(
                id=graph_message.id,
                sender='user' if message_type == 'human' else 'speck',
                content=graph_message.content,
                created_at=user_message_created_at if message_type == 'human' else pendulum.now(),
            )
            self.messages.append(message)

        # Return the final message
        return message
