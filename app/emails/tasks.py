from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

from config import celery_app, db_engine

from .models import Mailbox


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

    mailbox.sync_inbox()
