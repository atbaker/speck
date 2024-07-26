import pendulum
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select
from typing import Any, Dict, List, Optional

from config import db_engine
from library import speck_library

from .models import Mailbox, Message, SelectedFunctionArgument


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
    if mailbox.last_synced_at and pendulum.now() - pendulum.instance(mailbox.last_synced_at) < pendulum.Duration(seconds=30):
        return

    mailbox.sync_inbox()

def process_new_message(message_id: int):
    """
    Process a new message.
    """
    with Session(db_engine) as session:
        try:
            message = session.exec(select(Message).where(Message.id == message_id)).one()
            message.mailbox
        except NoResultFound:
            # If we didn't find a Message, then do nothing
            return

    message.analyze_and_process()

    with Session(db_engine) as session:
        session.add(message)
        session.commit()

def execute_function_for_message(
        message_id: str,
        function_name: str
    ):
    """
    Execute a Speck Function based on a message.
    """
    with Session(db_engine) as session:
        try:
            message = session.exec(select(Message).where(Message.id == message_id)).one()
        except NoResultFound:
            raise ValueError(f"Message {message_id} not found, cannot execute function {function_name}")

    # Execute the function
    message.execute_function(function_name)

    # Save the results
    with Session(db_engine) as session:
        session.add(message)
        session.commit()
