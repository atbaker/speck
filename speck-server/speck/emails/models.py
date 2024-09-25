import base64
from datetime import datetime
import enum
import email
from googleapiclient.errors import HttpError as GoogleApiHttpError
import uuid
import html2text
import logging
import pendulum
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, Enum, ForeignKey, DateTime, Integer, String, select, delete, text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlite_vec import serialize_float32
from typing import List, Literal, Optional

from config import db_engine
from core.models import Base
from core.utils import generate_embedding, generate_completion_with_validation
from core.task_manager import task_manager
from library import speck_library, FunctionResult

from .utils import get_gmail_api_client

logger = logging.getLogger(__name__)


class Mailbox(Base):
    __tablename__ = 'mailbox'

    id: Mapped[int] = mapped_column(primary_key=True)

    email_address: Mapped[str] = mapped_column(String(60), unique=True)

    last_history_id: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)

    threads: Mapped[list['Thread']] = relationship(
        back_populates='mailbox',
        cascade='all, delete'
    )

    messages: Mapped[list['Message']] = relationship(
        back_populates='mailbox',
        cascade='all, delete'
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # profile: Optional["Profile"] = Relationship(back_populates="mailbox", sa_relationship_kwargs={"uselist": False})

    def full_sync(self):
        """
        Sync the Mailbox with the Gmail API.

        - Fetch all threads currently in the user's inbox
        - And all threads with messages received in the past 31 days
        - Fetch the messages in each thread and create Message objects for them
        - Delete old Thread and Message objects for emails that no longer meet
          the above criteria
        """
        client = get_gmail_api_client()

        # Initialize our thread_ids set and last_synced_at
        thread_ids = set()
        last_synced_at = pendulum.now('utc')

        # First, get the threads ids for all threads in the user's inbox
        while True:
            response = client.users().threads().list(userId='me', labelIds=['INBOX'], maxResults=500).execute()
            thread_ids.update([thread['id'] for thread in response['threads']])
            if 'nextPageToken' not in response:
                break
            next_page_token = response['nextPageToken']
            logging.info(f"Fetched {len(thread_ids)} inbox threads so far, fetching next page...")

        # Next, fetch all threads with messages received in the past 31 days
        after_date = pendulum.now('utc').subtract(days=32) # 32 to be safe
        next_page_token = None
        while True:
            response = client.users().threads().list(userId='me', q=f'after:{after_date.format("YYYY/MM/DD")}', pageToken=next_page_token).execute()
            thread_ids.update([thread['id'] for thread in response['threads']])
            if 'nextPageToken' not in response:
                break
            next_page_token = response['nextPageToken']
            logging.info(f"Fetched {len(thread_ids)} non-inbox threads so far, fetching next page...")

        # Sync each Thread, which will also sync all of its Messages, keeping
        # track of the most recent history_id
        most_recent_history_id = 0
        for thread_id in thread_ids:
            thread = self.sync_thread(thread_id)
            most_recent_history_id = max(most_recent_history_id, thread.history_id)

        with Session(db_engine) as session:
            # Delete old Message, VecMessage, and Thread objects which are no
            # longer in our set, using a subquery because VecMessage doesn't
            # have a thread_id field
            # subquery = select(Message.id).where(Message.thread_id.not_in(thread_ids))
            # session.execute(delete(VecMessage).where(VecMessage.message_id.in_(subquery)).execution_options(is_delete_using=True))
            session.execute(delete(Message).where(Message.thread_id.not_in(thread_ids)))
            session.execute(delete(Thread).where(Thread.id.not_in(thread_ids)))

            # Update the Mailbox's last_history_id and last_synced_at
            self.last_history_id = most_recent_history_id
            self.last_synced_at = last_synced_at
            session.add(self)
            session.commit()

            # Also schedule a task to update the Profile if it's not complete
            from profiles.models import Profile
            profile = session.execute(select(Profile)).scalar_one() # TODO: Multiple profiles
            if not profile.complete:
                from profiles.tasks import update_profile
                # TODO: Reenable later
                # task_manager.add_task(
                #     task=update_profile
                # )

    def sync(self):
        """
        Sync the mailbox using the Gmail history API, using the Mailbox's
        last_history_id.
        """
        # If our Mailbox doesn't have a last_history_id, then we need to
        # perform a full sync instead
        if not self.last_history_id:
            self.full_sync()
            return

        # Before we begin this new sync, check if any of our existing Threads
        # and Messages are unprocessed
        with Session(db_engine) as session:
            unprocessed_threads = session.execute(
                select(Thread).where(Thread.processed == False)
            ).scalars().all()
            for thread in unprocessed_threads:
                from .tasks import process_inbox_thread
                task_manager.add_task(
                    task=process_inbox_thread,
                    queue_name='completion',
                    thread_id=thread.id
                )

            unprocessed_messages = session.execute(
                select(Message).where(Message.embedding_generated == False)
            ).scalars().all()
            for message in unprocessed_messages:
                from .tasks import generate_embedding_for_message
                task_manager.add_task(
                    task=generate_embedding_for_message,
                    queue_name='embedding',
                    message_id=message.id
                )

        # Make a request to the Gmail history API using our last_history_id
        client = get_gmail_api_client()
        last_synced_at = pendulum.now('utc')
        try:
            response = client.users().history().list(
                userId='me',
                startHistoryId=self.last_history_id,
                maxResults=500, # Maximum allowed value
            ).execute()
        except GoogleApiHttpError as e:
            if e.status_code == 404:
                # If the error is a 404, then our last_history_id is too old
                # and we need to perform a full sync
                self.full_sync()
                return
            else:
                raise e

        # Iterate over each history entry, identifying which Threads changed, so
        # we can sync them each (vs. trying to parse the history entries)
        thread_ids = set()
        for history_entry in response.get('history', []):
            # Delete messages which were deleted in this history entry (we'll
            # clean up orphan Threads later)
            for message_deleted_entry in history_entry.get('messagesDeleted', []):
                thread_ids.add(message_deleted_entry['message']['threadId'])

            # Otherwise, check the other three potential types of history entries
            # (messages changed, messages added, messages labeled)
            for message_added_entry in history_entry.get('messagesAdded', []):
                thread_ids.add(message_added_entry['message']['threadId'])

            for label_added_entry in history_entry.get('labelAdded', []):
                thread_ids.add(label_added_entry['message']['threadId'])

            for label_removed_entry in history_entry.get('labelRemoved', []):
                thread_ids.add(label_removed_entry['message']['threadId'])

        # Sync each Thread
        for thread_id in thread_ids:
            self.sync_thread(thread_id)

        # Update the Mailbox's last_history_id and last_synced_at
        with Session(db_engine) as session:
            self.last_history_id = response['historyId']
            self.last_synced_at = last_synced_at
            session.add(self)
            session.commit()

        # If there was a nextPageToken in our response, then there are more
        # history updates available and we should sync again
        if 'nextPageToken' in response:
            self.sync()

    def sync_thread(self, thread_id: str):
        """
        Sync a single thread from the Gmail API by its ID.
        """
        client = get_gmail_api_client()

        # Get or create the Thread
        with Session(db_engine) as session:
            try:
                statement = select(Thread).where(Thread.id == thread_id, Thread.mailbox_id == self.id)
                thread = session.execute(statement).scalar_one()
            except NoResultFound:
                thread = Thread(id=thread_id, mailbox_id=self.id)

        # Get this Thread from the Gmail API
        logging.info(f"Fetching thread {thread_id} from Gmail")
        try:
            response = client.users().threads().get(userId='me', id=thread_id, format='minimal').execute()
        except GoogleApiHttpError as e:
            if e.status_code == 404:
                logging.info(f"Thread {thread_id} has been deleted from the user's mailbox")

                # Delete this Thread and its VecMessages and Messages (if any) from the database
                with Session(db_engine) as session:
                    # subquery = select(Message.id).where(Message.thread_id == thread_id)
                    # session.execute(delete(VecMessage).where(VecMessage.message_id.in_(subquery)).execution_options(is_delete_using=True))
                    session.execute(delete(Message).where(Message.thread_id == thread_id))
                    session.execute(delete(Thread).where(Thread.id == thread_id))

                return
            else:
                raise e

        # Set the history_id on the Thread
        thread.history_id = response['historyId']

        # Sync each Message in the Thread
        thread_message_ids = [message['id'] for message in response['messages']]
        for message_id in thread_message_ids:
            self.sync_message(message_id)

        with Session(db_engine) as session:
            # Delete any Messages which used to be in the Thread but aren't anymore
            session.execute(
                delete(Message).where(
                    Message.thread_id == thread_id,
                    Message.id.not_in(thread_message_ids)
                )
            )

            # Commit the Thread to the database
            session.add(thread)
            session.commit()

            # If the thread needs to be processed, schedule it
            if not thread.processed:
                from .tasks import process_inbox_thread
                task_manager.add_task(
                    task=process_inbox_thread,
                    queue_name='completion',
                    thread_id=thread_id
                )

        return thread

    def sync_message(self, message_id: str):
        """
        Sync a single message from the Gmail API by its ID.
        """
        client = get_gmail_api_client()

        # Get or create the Message
        with Session(db_engine) as session:
            try:
                statement = select(
                    Message
                ).where(
                    Message.id == message_id,
                    Message.mailbox_id == self.id
                )
                message = session.execute(statement).scalar_one()
            except NoResultFound:
                message = Message(
                    id=message_id,
                    mailbox_id=self.id,
                )

        # Get the raw data from Gmail for this message
        logging.info(f"Fetching message {message_id} from Gmail")
        try:
            response = client.users().messages().get(userId='me', id=message_id, format='raw').execute()
        except GoogleApiHttpError as e:
            # If the error is a 404, then the message has been deleted from the
            # user's mailbox and we don't need to sync it
            if e.status_code == 404:
                logging.info(f"Message {message_id} has been deleted from the user's mailbox")

                # Delete the Message and its VecMessage from the database
                with Session(db_engine) as session:
                    # session.execute(delete(VecMessage).where(VecMessage.message_id == message_id))
                    session.execute(delete(Message).where(Message.id == message_id))

                return
            else:
                raise e

        # Convert the raw data into an Email object
        message.raw = base64.urlsafe_b64decode(response['raw'])
        email_message = email.message_from_bytes(
            message.raw,
            policy=email.policy.default
        )

        # Parse the recipients and the body
        to_recipients = [recipient.strip() for recipient in email_message['To'].split(',')] if email_message['To'] else []
        cc_recipients = [recipient.strip() for recipient in email_message['Cc'].split(',')] if email_message['Cc'] else []
        bcc_recipients = [recipient.strip() for recipient in email_message['Bcc'].split(',')] if email_message['Bcc'] else []

        # Parse the date into a datetime
        received_at = pendulum.from_timestamp(int(response['internalDate']) / 1000)

        # Update the fields on the Message
        message.history_id = response['historyId']
        message.thread_id = response['threadId']
        message.label_ids = response['labelIds']
        message.from_ = email_message['From']
        message.to = to_recipients
        message.cc = cc_recipients
        message.bcc = bcc_recipients
        message.subject = email_message['Subject']
        message.received_at = received_at

        # Use html2text to process the body
        text_maker = html2text.HTML2Text()
        text_maker.ignore_images = True
        text_maker.ignore_links = True

        try:
            content = email_message.get_body(preferencelist=('html', 'text')).get_content()
            message.body = text_maker.handle(content)
        except AttributeError:
            # If the message doesn't have a body, like a calendar invitation,
            # just set its body to an empty string for now
            logging.info(f"Message {message_id} doesn't have a body, skipping")
            message.body = ''

        # Commit our message
        with Session(db_engine) as session:
            session.add(message)
            session.commit()

            # If the message hasn't been processed, generate an embedding for it
            if not message.embedding_generated:
                from .tasks import generate_embedding_for_message
                task_manager.add_task(
                    task=generate_embedding_for_message,
                    queue_name='embedding',
                    message_id=message_id
                )

        return message

    def get_general_context(self):
        """Get the general context of the mailbox, to be used in prompts."""
        general_context = f"""
        <general-context>
            <current-utc-datetime>{ str(pendulum.now('utc')) }</current-utc-datetime>
            <user-email-address>{ self.email_address }</user-email-address>
        </general-context>
        """
        return general_context

    def get_thread(self, thread_id: str):
        """Get the details of a thread."""
        with Session(db_engine) as session:
            thread = session.execute(
                select(Thread).where(Thread.mailbox_id == self.id, Thread.id == thread_id)
            ).scalar_one()

            # Access the thread's messages to avoid lazy loading errors
            thread.messages

        return thread

    def get_threads(self):
        """Get all the threads in the mailbox."""
        with Session(db_engine) as session:
            threads = session.execute(
                select(Thread).where(Thread.mailbox_id == self.id)
            ).scalars().all()

        mailbox_data = {}
        for thread in threads:
            mailbox_data[thread.id] = {
                'id': thread.id,
                'category': thread.category,
                'summary': thread.summary,
                'selected_functions': thread.selected_functions,
                'executed_functions': thread.executed_functions,
            }
        return mailbox_data

    def list_threads(self, max_results: int = 100):
        """List the threads in the mailbox."""
        with Session(db_engine) as session:
            threads = session.execute(
                select(Thread).where(Thread.mailbox_id == self.id).order_by(Thread.history_id.desc()).limit(max_results)
            ).scalars().all()

        return threads

    def search_embeddings(self, query: str, k: int = 10):
        """Search the mailbox's embeddings for a query."""
        # Generate an embedding for the query
        query_embedding = generate_embedding(query)
        serialized_query_embedding = serialize_float32(query_embedding)

        # Run the query against the VecMessage table to find the 10 most similar messages
        with Session(db_engine) as session:
            results = session.execute(text(
                'select * from vec_message where body_embedding match :query_embedding limit :k'
            ).bindparams(
                query_embedding=serialized_query_embedding,
                k=k
            )).scalars().all()

            # Get the message_ids from the results
            message_ids = [message_id for message_id, embedding in results]

            # Get the messages from the Message table
            messages = session.execute(
                select(Message).where(Message.id.in_(message_ids))
            ).scalars().all()

        return messages

    def insert_message(self):
        """Insert a message into the user's inbox."""
        client = get_gmail_api_client()

        # Create a simple test message
        message = {
            'raw': base64.urlsafe_b64encode(
                b"From: test@example.com\r\n"
                b"To: me\r\n"
                b"Subject: Test Message\r\n\r\n"
                b"This is a test message."
            ).decode('utf-8')
        }

        # Insert the message into the user's inbox
        response = client.users().messages().insert(
            userId='me',
            body=message
        ).execute()

        logging.info(f"Inserted message with ID: {response['id']}")


class ThreadCategory(str, enum.Enum):
    CORRESPONDENCE = 'Correspondence'
    PROFESSIONAL_OPPORTUNITIES = 'Professional Opportunities'
    RECEIPTS = 'Receipts'
    BILLS_AND_STATEMENTS = 'Bills and Statements'
    PROMOTIONS_AND_DEALS = 'Promotions and Deals'
    NEWSLETTERS = 'Newsletters'
    UPDATES = 'Updates'
    ORDER_CONFIRMATIONS = 'Order Confirmations'
    PRODUCT_RECOMMENDATIONS = 'Product Recommendations'
    TICKETS_AND_BOOKINGS = 'Tickets and Bookings'
    COURSES_AND_LEARNING = 'Courses and Learning'
    ORGANIZATIONAL_ANNOUNCEMENTS = 'Organizational Announcements'
    UTILITIES_AND_SERVICES = 'Utilities and Services'
    SECURITY_ALERTS = 'Security Alerts'
    SERVICE_NOTIFICATIONS = 'Service Notifications'
    SURVEYS_AND_FEEDBACK = 'Surveys and Feedback'
    POLITICAL = 'Political'
    SPAM = 'Spam'
    HEALTH_AND_WELLNESS = 'Health and Wellness'
    MISCELLANEOUS = 'Miscellaneous'

THREAD_CATEGORY_DESCRIPTIONS = {
    ThreadCategory.CORRESPONDENCE: "Emails from individuals, including personal and professional communications.",
    ThreadCategory.PROFESSIONAL_OPPORTUNITIES: "Job opportunities, application statuses, career opportunities, and professional networking emails.",
    ThreadCategory.RECEIPTS: "Purchase confirmations, order receipts, and transaction details.",
    ThreadCategory.BILLS_AND_STATEMENTS: "Utility bills, credit card statements, bank statements, and loan notices.",
    ThreadCategory.PROMOTIONS_AND_DEALS: "Promotional emails, discount offers, coupons, and sales alerts.",
    ThreadCategory.NEWSLETTERS: "Regular email updates from subscribed newsletters, blogs, and websites.",
    ThreadCategory.UPDATES: "Updates from services or products, software updates, and feature announcements.",
    ThreadCategory.ORDER_CONFIRMATIONS: "Order confirmations and shipping notifications from online purchases.",
    ThreadCategory.PRODUCT_RECOMMENDATIONS: "Emails recommending products based on previous purchases or browsing history.",
    ThreadCategory.TICKETS_AND_BOOKINGS: "Travel itineraries, flight confirmations, hotel bookings, concert tickets, sports events, theater tickets, and event invitations.",
    ThreadCategory.COURSES_AND_LEARNING: "Online course updates, class schedules, and educational content.",
    ThreadCategory.ORGANIZATIONAL_ANNOUNCEMENTS: "Emails from educational institutions, company-wide emails from employers, and announcements from non-professional organizations.",
    ThreadCategory.UTILITIES_AND_SERVICES: "Notifications from utility providers, service updates, maintenance notices, internet, cable, phone providers, and other service companies.",
    ThreadCategory.SECURITY_ALERTS: "Account security notifications, password resets, and suspicious activity alerts.",
    ThreadCategory.SERVICE_NOTIFICATIONS: "Notifications from apps and services, error messages, and system alerts.",
    ThreadCategory.SURVEYS_AND_FEEDBACK: "Requests for feedback, surveys, and user experience questionnaires.",
    ThreadCategory.POLITICAL: "Political emails, including donation requests and campaign updates.",
    ThreadCategory.SPAM: "Unwanted emails, phishing attempts, and known spam.",
    ThreadCategory.HEALTH_AND_WELLNESS: "Emails from healthcare providers, appointment reminders, and health-related updates.",
    ThreadCategory.MISCELLANEOUS: "An email which does not fit any other category."
}

class SelectedFunctionArgument(BaseModel):
    name: str
    value: str

    def as_kwarg(self):
        return {self.name: self.value}

class SelectedFunction(BaseModel):
    name: str
    arguments: Optional[List[SelectedFunctionArgument]] = None
    button_text: str
    reason: str

    @field_validator('name')
    def name_must_exist_in_speck_library(cls, v):
        if v not in speck_library.functions:
            raise ValueError(f"Function '{v}' is not in the Speck library. Do not invent new functions, only return functions that are already in the Speck library. If no function is relevant, set the 'no_functions_selected' field to true.")
        return v

    def get_args_as_kwargs(self):
        return {arg.name: arg.value for arg in self.arguments}

class ExecutedFunction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    arguments: Optional[List[SelectedFunctionArgument]] = None
    status: Literal['pending', 'success', 'error'] = 'pending'
    result: FunctionResult | None = None

class Thread(Base):
    __tablename__ = 'thread'

    id: Mapped[str] = mapped_column(String(16), primary_key=True)

    mailbox_id: Mapped[int] = mapped_column(ForeignKey('mailbox.id'))
    mailbox: Mapped["Mailbox"] = relationship(back_populates='threads')

    history_id: Mapped[int] = mapped_column(Integer)

    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates='thread',
        cascade='all, delete',
        lazy='subquery',
        order_by='desc(Message.received_at)'
    )

    category: Mapped[Optional[ThreadCategory]] = mapped_column(Enum(ThreadCategory))
    summary: Mapped[Optional[str]] = mapped_column(String(80))

    selected_functions: Mapped[dict[str, SelectedFunction]] = mapped_column(JSON, default=dict)
    executed_functions: Mapped[dict[str, ExecutedFunction]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def in_inbox(self):
        """Returns True if the thread has a message in the user's inbox."""
        return any(message.in_inbox for message in self.messages)

    def get_details(self):
        """
        Renders the details for this thread and its messages, to be used in prompts.
        """
        message_details = '\n'.join([message.get_details() for message in self.messages])

        thread_details = f"""
        <email-thread>
            { '<thread-category>' + self.category.value + '</thread-category>' if self.category else ''}
            { '<thread-summary>' + self.summary + '</thread-summary>' if self.summary else ''}
            <email-messages>
                { message_details }
            </email-messages>
        </email-thread>
        """

        return thread_details
    
    def analyze_and_process(self):
        """
        Analyze and process this thread:
        
        - Categorize the thread
        - Summarize the thread
        - Select relevant Speck Functions for this thread
        """
        # If this Thread has already been processed, do nothing
        if self.processed:
            return

        # If the Thread isn't currently in the user's inbox, we don't need to
        # do any work and can mark it as processed
        if not self.in_inbox:
            self.processed = True
            return

        prompt_template = """
        <context>
        {{ thread_details }}
        {{ general_context }}
        </context>

        <instructions>
        <overall-instructions>
        Analyze this email thread from the user's inbox by completing three tasks: categorizing the thread, generating a short summary, and selecting relevant Speck Functions to execute.
        </overall-instructions>

        <task-one-categorize>
        <task-instructions>
        Categorize this email thread into one of the categories listed below. When deciding between multiple categories, choose the one that best fits the most recently received message. If no category fits well, use the "Miscellaneous" category.
        </task-instructions>
        <category-descriptions>
        {% for category, description in category_descriptions.items() %}
        <category>
        <name>
        {{ category.value }}
        </name>
        <description>
        {{ description }}
        </description>
        </category>
        {% endfor %}
        </category-descriptions>
        </task-one-categorize>

        <task-two-summarize>
        <task-instructions>
        Generate a short summary of this email thread. Focus on the main point of the thread and any actionable items for the user. In threads with many messages, focus on the most recent messages.
        </task-instructions>
        </task-two-summarize>

        <task-three-function-selection>
        <task-instructions>
        Speck Functions are actions that an AI assistant can perform on behalf of the user. Based on the contents of the email the user received, determine which Speck Functions, if any, are relevant to the message. If a function is relevant, identify which function, the arguments it should use based on the message, the text the UI button should display, and the reason for the function's relevance to this email message. For most threads, no Speck Functions will be relevant, and so you should set the 'no_functions_selected' field to true. Do not invent new functions, only return functions that are already in the Speck Function Library.
        </task-instructions>
        <speck-function-library>
        {% for func_name, func_details in speck_function_library.functions.items() %}
        <speck-function>
        <name>
        {{ func_name }}
        </name>
        <parameters>
        {{ func_details.parameters }}
        </parameters>
        <description>
        {{ func_details.description }}
        </description>
        </speck-function>
        {% endfor %}
        </speck-function-library>
        </task-three-function-selection>
        </instructions>
        """

        partial_variables = {
            'category_descriptions': THREAD_CATEGORY_DESCRIPTIONS,
            'speck_function_library': speck_library
        }

        class ThreadAnalysis(BaseModel):
            category: ThreadCategory
            summary: str = Field(max_length=80)
            no_functions_selected: bool = Field(default=True)
            selected_functions: Optional[List[SelectedFunction]] = None

        input_variables = {
            'general_context': self.mailbox.get_general_context(),
            'thread_details': self.get_details()
        }

        result = generate_completion_with_validation(
            prompt_template=prompt_template,
            partial_variables=partial_variables,
            input_variables=input_variables,
            output_model=ThreadAnalysis,
            llm_temperature=0
        )

        self.category = result.category
        self.summary = result.summary
        if result.selected_functions is not None:
            self.selected_functions = {func.name: func.model_dump_json() for func in result.selected_functions}

        self.processed = True

    def execute_function(self, function_name: str):
        """Execute a Speck Function based on this message."""
        # Get the SelectedFunction
        selected_function = SelectedFunction.model_validate_json(
            self.selected_functions[function_name]
        )

        # Run the function
        result = speck_library.execute_function(
            function_name=selected_function.name,
            arguments=selected_function.get_args_as_kwargs()
        )

        # Create an ExecutedFunction object
        executed_function = ExecutedFunction(
            name=selected_function.name,
            arguments=selected_function.arguments,
            status='success' if result.success else 'error',
            result=result
        )

        # TODO: SQLAlchemy can't track mutations of JSON dicts without using a custom type,
        # so for now just replace the whole dict
        self.executed_functions = {
            **self.executed_functions,
            executed_function.id: executed_function.model_dump_json()
        }

class Message(Base):
    __tablename__ = 'message'

    id: Mapped[str] = mapped_column(String(16), primary_key=True)

    mailbox_id: Mapped[int] = mapped_column(ForeignKey('mailbox.id'))
    mailbox: Mapped["Mailbox"] = relationship(back_populates='messages')

    raw: Mapped[str] = mapped_column(String)
    history_id: Mapped[int] = mapped_column(Integer)

    thread_id: Mapped[str] = mapped_column(ForeignKey('thread.id'))
    thread: Mapped["Thread"] = relationship(back_populates='messages')

    label_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    from_: Mapped[str] = mapped_column(String)
    to: Mapped[list[str]] = mapped_column(JSON, default=list)
    cc: Mapped[list[str]] = mapped_column(JSON, default=list)
    bcc: Mapped[list[str]] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    body: Mapped[str] = mapped_column(String)

    embedding_generated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def in_inbox(self):
        """Returns True if the message is in the user's inbox."""
        return 'INBOX' in self.label_ids

    def get_details(self):
        """
        Renders the message details for this message, to be used in prompts.
        """
        message_details = f"""
        <email-message-user-received>
            <from>{ self.from_ }</from>
            <to>{ self.to }</to>
            <cc>{ self.cc }</cc>
            <bcc>{ self.bcc }</bcc>
            <subject>{ self.subject }</subject>
            <received-at>{ self.received_at }</received-at>
            <body>
            { self.body }
            </body>
        </email-message-user-received>
        """

        return message_details

    def generate_embedding(self):
        """Generate an embedding for the message."""
        # TODO: Re-enable embeddings later
        return

        # If this message has a blank body, we don't need to generate an embedding
        if not self.body:
            with Session(db_engine) as session:
                self.embedding_generated = True
                session.add(self)
                session.commit()
                return

        # Check if we already have an embedding
        with Session(db_engine) as session:
            try:
                session.execute(
                    select(VecMessage).where(VecMessage.message_id == self.id)
                ).scalar_one()

                # If we do, return
                return
            except NoResultFound:
                # If we don't, generate it
                pass

        # Generate the embedding
        embedding = generate_embedding(self.body)

        # Convert the result to a BLOB
        embedding_blob = serialize_float32(embedding)

        # Save it as a new VecMessage object and set the embedding_generated flag
        with Session(db_engine) as session:
            vec_message = VecMessage(
                message_id=self.id,
                body_embedding=embedding_blob
            )
            session.add(vec_message)

            self.embedding_generated = True
            session.add(self)

            session.commit()

# class VecMessage(SQLModel, table=True):
#     """
#     A virtual table that stores the embeddings of the messages.

#     NOTE: This is a virtual table that is created using the sqlite-vec extension,
#     not by SQLModel.
#     """
#     message_id: str = SQLModelField(primary_key=True)

#     body_embedding: bytes = SQLModelField(sa_column=Column(BLOB))

#     @declared_attr
#     def __tablename__(cls) -> str:
#         return 'vec_message'
