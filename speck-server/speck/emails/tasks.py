import logging
import pendulum
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select
from typing import Any, Dict, List, Optional

from config import db_engine
from library import speck_library

from .models import Mailbox, Message, Thread

logger = logging.getLogger(__name__)


def sync_inbox():
    """
    Sync the local Mailbox with the user's Gmail inbox.
    """
    with Session(db_engine) as session:
        try:
            # TODO: Enhance to support multiple mailboxes
            mailbox = session.exec(select(Mailbox)).one()
        except NoResultFound:
            # If we didn't find a Mailbox, then do nothing
            return

    # If we last synced less than 30 seconds ago, skip this sync
    if mailbox.last_synced_at and (pendulum.now('utc') - pendulum.instance(mailbox.last_synced_at)).in_seconds() < 30:
        logger.info("Skipping inbox sync because it was last synced less than 30 seconds ago")
        return

    mailbox.sync()

def process_inbox_thread(thread_id: int):
    """
    Process a thread which has a message in the user's inbox.
    """
    with Session(db_engine) as session:
        try:
            thread = session.exec(select(Thread).where(Thread.id == thread_id)).one()
            thread.mailbox
        except NoResultFound:
            # If we didn't find a Message, then do nothing
            return

    thread.analyze_and_process()

    with Session(db_engine) as session:
        session.add(thread)
        session.commit()

def generate_embedding_for_message(message_id: int):
    """
    Generate an embedding for a given message.
    """
    with Session(db_engine) as session:
        message = session.exec(select(Message).where(Message.id == message_id)).one()

    message.generate_embedding()

def execute_function_for_message(
        thread_id: str,
        function_name: str
    ):
    """
    Execute a Speck Function based on a message.
    """
    with Session(db_engine) as session:
        try:
            message = session.exec(select(Message).where(Message.thread_id == thread_id)).one()
        except NoResultFound:
            raise ValueError(f"Message {thread_id} not found, cannot execute function {function_name}")

    # Execute the function
    message.execute_function(function_name)

    # Save the results
    with Session(db_engine) as session:
        session.add(message)
        session.commit()
