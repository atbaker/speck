import base64
from datetime import datetime
import email
import pendulum
from pydantic import BaseModel, Field
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.exc import NoResultFound
from sqlmodel import Column, Field, Session, SQLModel, Relationship, select, delete
from typing import List
from unstructured.partition.email import partition_email

from config import db_engine
from core.utils import run_instructor_completion

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
        new_message_ids = []
        with session or Session(db_engine) as session:
            for message_id in message_ids:
                # If we have a Message record for this message_id, then assume
                # the message hasn't changed and skip this record
                try:
                    statement = select(
                        Message
                    ).where(
                        Message.id == message_id,
                        Message.mailbox_id == self.id
                    )
                    message = session.exec(statement).one()
                    continue
                except NoResultFound:
                    message = Message(
                        id=message_id,
                        mailbox_id=self.id,
                    )
                    new_message_ids.append(message_id)

                # Get the raw data from Gmail for this message
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
                message.raw = email_message.as_string()

                # Parse the recipients and the body
                to_recipients = [recipient.strip() for recipient in email_message['To'].split(',')] if email_message['To'] else []
                cc_recipients = [recipient.strip() for recipient in email_message['Cc'].split(',')] if email_message['Cc'] else []
                bcc_recipients = [recipient.strip() for recipient in email_message['Bcc'].split(',')] if email_message['Bcc'] else []

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

                # Use Unstructured to pre-process the body
                message.process_body()

                session.add(message)

            # Update the Mailbox's last_synced_at
            self.last_synced_at = last_synced_at
            session.add(self)

            # Delete old Message objects for emails that are no longer in the inbox
            session.exec(delete(Message).where(Message.id.not_in(message_ids)))

            # Generate summaries for new messages
            for message_id in new_message_ids:
                from .tasks import generate_message_summary
                generate_message_summary.delay(message_id)

            session.commit()


class Message(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)

    mailbox_id: int = Field(default=None, foreign_key='mailbox.id')
    mailbox: Mailbox = Relationship(back_populates='messages')

    raw: str

    thread_id: str
    label_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    from_: str
    to: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    cc: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    bcc: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    subject: str
    received_at: datetime
    body: str

    summary: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)

    def process_body(self):
        """Use Unstructured to process the raw email into a clean body."""
        elements = partition_email(
            text=self.raw,
        )

        # Keep things simple for now and just set the body field to
        # a concatenated string of each element's metadata + text
        self.body = '\n\n\n'.join([
            f'{element.metadata.to_dict()}\n\n{element.text}'
            for element in elements
        ])

    def generate_summary(self):
        """Generate and store a short summary of the message."""
        class MessageSummary(BaseModel):
            summary: str = Field(max_length=80)

        prompt = f'Using the context: {self.body}\n\nSummarize this email into one phrase of maximum 80 characters. Focus on the main point of the message and any actionable items for the user.'
        result = run_instructor_completion(
            model=MessageSummary,
            prompt=prompt
        )
        self.summary = result.summary
