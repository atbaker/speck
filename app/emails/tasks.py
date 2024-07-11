import pendulum
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

from config import celery_app, db_engine

from .models import Mailbox, Message


@celery_app.task
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


@celery_app.task
def process_new_message(message_id: int):
    """
    Process a new message.
    """
    with Session(db_engine) as session:
        try:
            message = session.exec(select(Message).where(Message.id == message_id)).one()
        except NoResultFound:
            # If we didn't find a Message, then do nothing
            return

    message.analyze_and_process()

    with Session(db_engine) as session:
        session.add(message)
        session.commit()
