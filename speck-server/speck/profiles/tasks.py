

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound


from config import db_engine
from .models import Profile


def update_profile():
    """
    Update a Profile, determining its attributes.
    """
    with Session(db_engine) as session:
        try:
            # TODO: Enhance to support multiple profiles
            profile = session.execute(select(Profile)).scalar_one()
            profile.mailbox
        except NoResultFound:
            # If we didn't find a Profile, then do nothing
            return

    profile.update()

    with Session(db_engine) as session:
        session.add(profile)
        session.commit()
