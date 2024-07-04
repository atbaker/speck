import base64
from datetime import datetime
import email
import pendulum
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.exc import NoResultFound
from sqlmodel import Column, Field, Session, SQLModel, Relationship, select, delete
from typing import List

from config import db_engine

from .utils import get_gmail_api_client


class Mailbox(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    email_address: str = Field(unique=True)

    last_history_id: int | None = None
    last_synced_at: datetime | None = None

    messages: list['Message'] = Relationship(back_populates='mailbox')

    created_at: datetime = Field(default_factory=datetime.now)

    def sync_inbox(self, session=None):
        """
        Sync the Mailbox with the Gmail API.

        - Fetch the list of emails currently in the user's inbox (limit to 100)
        - Create Message objects for new emails in the response
        - Delete old Message objects for emails that are no longer in the inbox
        """
        client = get_gmail_api_client()

        # Get all the message ids for messages in the user's inbox
        last_synced_at = pendulum.now()
        response = client.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=100).execute()
        message_ids = [message['id'] for message in response['messages']]

        # Iterate over each message and fetch its details
        with session or Session(db_engine) as session:
            for message_id in message_ids:
                # If we have a Message record for this message_id, then assume
                # the message hasn't changed and skip this record
                try:
                    message = session.exec(select(Message).where(Message.id == message_id, Message.mailbox_id == self.id)).one()
                    continue
                except NoResultFound:
                    message = Message(
                        id=message_id,
                        mailbox_id=self.id,
                    )

                # Get the data for this message
                response = client.users().messages().get(userId='me', id=message_id, format='raw').execute()

                # Update the Mailbox's last_history_id
                message_history_id = int(response['historyId'])
                if self.last_history_id is None or message_history_id > self.last_history_id:
                    self.last_history_id = message_history_id

                # Convert the raw data into an Email object
                email_message = email.message_from_bytes(
                    base64.urlsafe_b64decode(response['raw']),
                    policy=email.policy.default
                )

                # Parse the recipients and the body
                to_recipients = [recipient.strip() for recipient in email_message['To'].split(',')] if email_message['To'] else []
                cc_recipients = [recipient.strip() for recipient in email_message['Cc'].split(',')] if email_message['Cc'] else []
                bcc_recipients = [recipient.strip() for recipient in email_message['Bcc'].split(',')] if email_message['Bcc'] else []
                body = email_message.get_body(
                    preferencelist=('html', 'text')
                ).get_content()

                # Parse the date into a datetime
                received_at = pendulum.from_format(email_message['Date'], 'ddd, DD MMM YYYY HH:mm:ss Z')

                # Update the fields on the Message
                message.thread_id = response['threadId']
                message.label_ids = response['labelIds']
                message.from_ = email_message['From']
                message.to = to_recipients
                message.cc = cc_recipients
                message.bcc = bcc_recipients
                message.subject = email_message['Subject']
                message.received_at = received_at
                message.body = body

                session.add(message)

            # Update the Mailbox's last_synced_at
            self.last_synced_at = last_synced_at
            session.add(self)

            # Delete old Message objects for emails that are no longer in the inbox
            session.exec(delete(Message).where(Message.id.not_in(message_ids)))

            session.commit()


class Message(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)

    mailbox_id: int = Field(default=None, foreign_key='mailbox.id')
    mailbox: Mailbox = Relationship(back_populates='messages')

    thread_id: str
    label_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    from_: str
    to: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    cc: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    bcc: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    subject: str
    received_at: datetime
    body: str

    created_at: datetime = Field(default_factory=datetime.now)
