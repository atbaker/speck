import pendulum
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

from config import celery_app, db_engine
from core.llm_service_manager import use_inference_service

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
@use_inference_service
def generate_message_summary(message_id: int):
    """
    Generate a summary of a message.
    """
    with Session(db_engine) as session:
        message = session.exec(select(Message).where(Message.id == message_id)).one()

    # Release the session while we run the inference
    message.generate_summary()

    with Session(db_engine) as session:
        session.add(message)
        session.commit()
