import base64
from collections import defaultdict
from datetime import datetime
import enum
import email
from googleapiclient.errors import HttpError as GoogleApiHttpError
import html2text
import json
import uuid
import logging
import pendulum
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import BLOB, Boolean, CheckConstraint, Enum, ForeignKey, DateTime, Integer, String, select, delete, text
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
    __tablename__ = 'mailboxes'

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
            # Delete old Message and Thread objects which are no longer in the
            # result set
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
        The user's email address is { self.email_address }.
        The current UTC datetime is { str(pendulum.now('utc')) }.
        """
        return general_context

    def get_state(self):
        """Get the current state of the Mailbox, for use in the UI."""
        with Session(db_engine) as session:
            threads = self.threads

        state = {
            "id": self.id,
            "email_address": self.email_address,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "summary": "[placeholder for summary]",
            "threads": {
                thread.id: thread.get_state() for thread in threads
            }
        }

        return state

    def list_threads(self, search: str = None, max_results: int = 10):
        """List the threads in the mailbox. Used to power the `list_threads` tool."""
        # If we have a search query, use the search method to get our threads
        if search:
            threads = self.search(search, max_results)
        else:
            # Otherwise, just query for the most recently updated threads
            with Session(db_engine) as session:
                threads = session.execute(
                    select(Thread).where(Thread.mailbox_id == self.id).order_by(Thread.history_id.desc()).limit(max_results)
                ).scalars().all()

        return threads

    def search(self, query: str, max_results: int = 20):
        """
        Search the mailbox's messages using both vector search and full text search,
        combining the results using Reciprocal Rank Fusion (RRF).

        Implementation from: https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html#hybrid-approach-2-reciprocal-rank-fusion-rrf
        """
        # Set the RRF parameters
        k = max_results
        rrf_k = 60
        weight_vec = 0.6
        weight_fts = 1.0

        # Generate an embedding for the query
        query_embedding = generate_embedding(query)
        serialized_query_embedding = serialize_float32(query_embedding)

        # Vector search query
        vec_query = '''
        SELECT
            rowid,
            distance,
            ROW_NUMBER() OVER (ORDER BY distance) AS rank_number
        FROM (
            SELECT
                rowid,
                vec_distance_L2(body_embedding, :query_embedding) AS distance
            FROM messages
            WHERE mailbox_id = :mailbox_id AND body_embedding IS NOT NULL
            ORDER BY distance
            LIMIT :k
        )
        '''

        # FTS search query
        fts_query = '''
        SELECT
            rowid AS id,
            rank AS score,
            ROW_NUMBER() OVER (ORDER BY rank) AS rank_number
        FROM messages_fts
        WHERE messages_fts MATCH :query
        LIMIT :k
        '''

        # Execute the queries
        with Session(db_engine) as session:
            vec_results = session.execute(
                text(vec_query),
                {'query_embedding': serialized_query_embedding, 'mailbox_id': self.id, 'k': k}
            ).fetchall()

            fts_results = session.execute(
                text(fts_query),
                {'query': query, 'k': k}
            ).fetchall()

        # Perform RRF fusion
        scores = defaultdict(float)
        for rowid, distance, rank_number in vec_results:
            scores[rowid] += weight_vec / (rrf_k + rank_number)

        for rowid, score, rank_number in fts_results:
            scores[rowid] += weight_fts / (rrf_k + rank_number)

        # Sort the results by the combined scores in descending order
        ranked_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Fetch Message objects
        message_rowids = [rowid for rowid, score in ranked_results[:max_results]]
        with Session(db_engine) as session:
            messages = session.execute(
                select(Message).where(Message.rowid.in_(message_rowids))
            ).scalars().all()

            # Sort messages according to the ranked order
            messages.sort(key=lambda m: message_rowids.index(m.rowid))

            # Convert the messages to a list of threads, maintaining the order
            threads = []
            for message in messages:
                thread = message.thread

                # Access thread.messages here to force a query
                # TODO: Find a more efficient way to do this
                thread.messages

                if thread not in threads:
                    threads.append(thread)

        return threads

    def search_embeddings(self, query: str, k: int = 10):
        """Search the mailbox's embeddings for a query."""
        # Generate an embedding for the query
        query_embedding = generate_embedding(query)
        serialized_query_embedding = serialize_float32(query_embedding)

        # Run the query against the VecMessage table to find the 10 most similar messages
        with Session(db_engine) as session:
            results = session.execute(
                text('SELECT id, vec_distance_L2(body_embedding, :query_embedding) AS distance FROM message WHERE mailbox_id = :mailbox_id AND body_embedding IS NOT NULL ORDER BY distance LIMIT :k').bindparams(
                    query_embedding=serialized_query_embedding,
                    mailbox_id=self.id,
                    k=k
                )
            ).all()

            # We need to retain the order of the results, so for now we'll just
            # create our messages list one-by-one
            messages = []
            for message_id, distance in results:
                message = session.execute(
                    select(Message).where(Message.id == message_id)
                ).scalar_one()
                messages.append(message)

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
    __tablename__ = 'threads'

    id: Mapped[str] = mapped_column(String(16), primary_key=True)

    mailbox_id: Mapped[int] = mapped_column(ForeignKey('mailboxes.id'))
    mailbox: Mapped["Mailbox"] = relationship(back_populates='threads')

    history_id: Mapped[int] = mapped_column(Integer)

    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates='thread',
        cascade='all, delete',
        lazy='selectin',
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

    def get_state(self):
        """Get the current state of the Thread, for use in the UI."""
        state = {
            "id": self.id,
            "mailbox_id": self.mailbox_id,
            "category": self.category,
            "summary": self.summary
        }
        return state

    def get_details(self, include_body: bool = False, as_string: bool = False):
        """
        Renders the details for this thread and its messages, to be used in prompts.
        """
        thread_details = {
            'id': self.id,
            'category': self.category,
            'summary': self.summary,
            'messages': [message.get_details(include_body=include_body, as_string=as_string) for message in self.messages]
        }

        # If we're not rendering as a string, we're done
        if not as_string:
            return thread_details

        # Otherwise, dump to a JSON string
        return json.dumps(thread_details)
    
    def analyze_and_process(self):
        """
        Analyze and process this thread:
        
        - Categorize the thread
        - Summarize the thread
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
        Analyze this email thread from the user's inbox, responding with a category and a summary.

        When deciding between multiple categories, choose the one that best fits the most recently received message. If no category fits well, use the "Miscellaneous" category.
        Your summary should be brief: 10-12 words, less than 80 characters. Focus on the main point of the thread and any actionable items for the user. In threads with many messages, focus on the most recent messages.

        {{ format_instructions }}

        Do not respond with any additional commentary outside of the JSON object.
        Enclose your response in triple backticks. Here's an example:
        ```
        {
            "category": "[your category here]",
            "summary": "[your summary here]"
        }
        ```

        General context: \"\"\"
        {{ general_context }}
        \"\"\"

        Thread details: \"\"\"
        {{ thread_details }}
        \"\"\"
        """

        partial_variables = {}

        class ThreadAnalysis(BaseModel):
            category: ThreadCategory
            summary: str = Field(max_length=100) # It's okay if the LLM overshoots the 80 char limit here

        input_variables = {
            'general_context': self.mailbox.get_general_context(),
            'thread_details': self.get_details(include_body=True, as_string=True)
        }

        result = generate_completion_with_validation(
            prompt_template=prompt_template,
            partial_variables=partial_variables,
            input_variables=input_variables,
            output_model=ThreadAnalysis,
            llm_temperature=0.2
        )

        self.category = result.category
        self.summary = result.summary

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
    __tablename__ = 'messages'

    rowid: Mapped[int] = mapped_column(Integer, primary_key=True) # Used for FTS
    id: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)

    mailbox_id: Mapped[int] = mapped_column(ForeignKey('mailboxes.id'))
    mailbox: Mapped["Mailbox"] = relationship(back_populates='messages')

    raw: Mapped[str] = mapped_column(String)
    history_id: Mapped[int] = mapped_column(Integer)

    thread_id: Mapped[str] = mapped_column(ForeignKey('threads.id'))
    thread: Mapped["Thread"] = relationship(
        back_populates='messages',
        lazy='selectin'
    )

    label_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    from_: Mapped[str] = mapped_column(String)
    to: Mapped[list[str]] = mapped_column(JSON, default=list)
    cc: Mapped[list[str]] = mapped_column(JSON, default=list)
    bcc: Mapped[list[str]] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    body: Mapped[str] = mapped_column(String)

    body_embedding: Mapped[Optional[bytes]] = mapped_column(
        BLOB,
        CheckConstraint(
            "(body_embedding IS NULL) OR (typeof(body_embedding) = 'blob' AND vec_length(body_embedding) = 768)",
            name='chk_body_embedding_valid'
        )
    )

    embedding_generated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def in_inbox(self):
        """Returns True if the message is in the user's inbox."""
        return 'INBOX' in self.label_ids

    def get_details(self, include_body: bool = False, as_string: bool = False):
        """
        Renders the message details for this message, to be used in prompts.
        """
        message_details = {
            'from': self.from_,
            'to': self.to,
            'cc': self.cc,
            'bcc': self.bcc,
            'subject': self.subject,
            'received_at': self.received_at,
        }

        if include_body:
            message_details['body'] = self.body

        # If we're not rendering as a string, we're done
        if not as_string:
            return message_details

        # Otherwise, adjust all unserializable values and render as a JSON string
        message_details['received_at'] = self.received_at.isoformat()

        return json.dumps(message_details)

    def generate_embedding(self):
        """Generate an embedding for the message."""
        # If this message already has an embedding or has a blank body, do nothing
        if self.body_embedding or not self.body:
            self.embedding_generated = True
            with Session(db_engine) as session:
                session.add(self)
                session.commit()
            return

        # Generate the embedding and convert it to a BLOB
        embedding = generate_embedding(self.body)
        self.body_embedding = serialize_float32(embedding)
        self.embedding_generated = True

        # Save this message
        with Session(db_engine) as session:
            session.add(self)
            session.commit()


class MessageFTS(Base):
    __tablename__ = 'messages_fts'

    rowid: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)
