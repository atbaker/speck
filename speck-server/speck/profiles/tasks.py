

from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

from config import db_engine
from .models import Profile


def update_profile():
    """
    Update a Profile, determining its attributes.
    """
    with Session(db_engine) as session:
        try:
            # TODO: Enhance to support multiple profiles
            profile = session.exec(select(Profile)).one()
            profile.mailbox
        except NoResultFound:
            # If we didn't find a Profile, then do nothing
            return

    profile.update()

    with Session(db_engine) as session:
        session.add(profile)
        session.commit()
