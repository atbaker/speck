import base64
from datetime import datetime
import enum
import email
import uuid
import html2text
import logging
import pendulum
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import declared_attr
from sqlite_vec import serialize_float32
from sqlmodel import Column, Enum, Field as SQLModelField, Session, SQLModel, Relationship, select, delete, text, bindparam, BLOB
from typing import List, Literal, Optional

from config import db_engine
from core.utils import generate_embedding, generate_completion_with_validation
from core.task_manager import task_manager
from library import speck_library, FunctionResult

from .utils import get_gmail_api_client

logger = logging.getLogger(__name__)


class Mailbox(SQLModel, table=True):
    id: int | None = SQLModelField(default=None, primary_key=True)

    email_address: str = SQLModelField(unique=True)

    last_history_id: int | None = None
    last_synced_at: datetime | None = None

    threads: list['Thread'] = Relationship(
        back_populates='mailbox',
        cascade_delete=True
    )
    messages: list['Message'] = Relationship(
        back_populates='mailbox',
        cascade_delete=True
    )

    created_at: datetime = SQLModelField(default_factory=datetime.now)

    # profile: Optional["Profile"] = Relationship(back_populates="mailbox", sa_relationship_kwargs={"uselist": False})

    def full_sync(self):
        """
        Sync the Mailbox with the Gmail API.

        - Fetch all emails currently in the user's inbox and the latest 1000 non-inbox emails
        - Create Message objects for new emails in the response
        - Delete old Message objects for emails that no longer meet the criteria
        """
        client = get_gmail_api_client()

        # Initialize our message_ids set and last_synced_at
        message_ids = set()
        last_synced_at = pendulum.now('utc')

        # First, get the message ids for messages in the user's inbox
        response = client.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=25).execute()
        message_ids.update([message['id'] for message in response['messages']])

        # Next, fetch non-inbox messages until our message_ids set has 500 items
        next_page_token = None
        while len(message_ids) < 500:  # TODO: Experiment with this number
            response = client.users().messages().list(userId='me', pageToken=next_page_token).execute()
            message_ids.update([message['id'] for message in response['messages']])
            if 'nextPageToken' not in response:
                break
            next_page_token = response['nextPageToken']
            logging.info(f"Fetched {len(message_ids)} messages so far, next page token: {next_page_token}")

        # Sync each Message, keeping track of the most recent history_id
        most_recent_history_id = 0
        for message_id in message_ids:
            message = self.sync_message(message_id)
            most_recent_history_id = max(most_recent_history_id, message.history_id)

        with Session(db_engine) as session:
            # Delete old Message objects for messages that are no longer in our set
            session.exec(delete(Message).where(Message.id.not_in(message_ids)))

            # Find and delete old Thread objects which no longer have any Messages
            thread_ids_to_delete = []
            for thread in session.exec(select(Thread)).all():
                if not thread.messages:
                    thread_ids_to_delete.append(thread.id)
            session.exec(delete(Thread).where(Thread.id.in_(thread_ids_to_delete)))

            # Update the Mailbox's last_history_id and last_synced_at
            self.last_history_id = most_recent_history_id
            self.last_synced_at = last_synced_at
            session.add(self)

            # Commit the changes
            session.commit()

            # Also schedule a task to update the Profile if it's not complete
            from profiles.models import Profile
            profile = session.exec(select(Profile)).one() # TODO: Multiple profiles
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

        client = get_gmail_api_client()
        last_synced_at = pendulum.now('utc')

        # Make a request to the Gmail history API using our last_history_id
        response = client.users().history().list(
            userId='me',
            startHistoryId=self.last_history_id,
            maxResults=500, # Maximum allowed value
        ).execute()

        # Iterate over each history entry
        message_ids = set()
        thread_ids_with_deleted_messages = set()
        for history_entry in response.get('history', []):
            # Delete messages which were deleted in this history entry (we'll
            # clean up orphan Threads later)
            for message_deleted_entry in history_entry.get('messagesDeleted', []):
                thread_ids_with_deleted_messages.add(message_deleted_entry['message']['threadId'])
                with Session(db_engine) as session:
                    session.exec(
                        delete(Message).where(
                            Message.id == message_deleted_entry['message']['id'],
                            Message.mailbox_id == self.id
                        )
                    )
                    session.commit()

            # Otherwise, check the other three potential types of history entries
            # (messages changed, messages added, messages labeled)
            for message_added_entry in history_entry.get('messagesAdded', []):
                message_ids.add(message_added_entry['message']['id'])

            for label_added_entry in history_entry.get('labelAdded', []):
                message_ids.add(label_added_entry['message']['id'])

            for label_removed_entry in history_entry.get('labelRemoved', []):
                message_ids.add(label_removed_entry['message']['id'])

        # Sync each Message
        for message_id in message_ids:
            self.sync_message(message_id)

        # Look at our set of thread_ids_with_deleted_messages and delete any
        # Threads which no longer have any Messages
        with Session(db_engine) as session:
            orphan_thread_ids = []
            for thread in session.exec(
                select(Thread).where(Thread.id.in_(thread_ids_with_deleted_messages))):
                if not thread.messages:
                    orphan_thread_ids.append(thread.id)
            session.exec(delete(Thread).where(Thread.id.in_(orphan_thread_ids)))

            # Update the Mailbox's last_history_id and last_synced_at
            self.last_history_id = response['historyId']
            self.last_synced_at = last_synced_at
            session.add(self)

            session.commit()

        # If there was a nextPageToken in our response, then thare are more
        # history updates available and we should sync again
        if 'nextPageToken' in response:
            self.sync()

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
                message = session.exec(statement).one()
            except NoResultFound:
                message = Message(
                    id=message_id,
                    mailbox_id=self.id,
                )

        # Get the raw data from Gmail for this message
        logging.info(f"Fetching message {message_id} from Gmail")
        response = client.users().messages().get(userId='me', id=message_id, format='raw').execute()

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
        received_at = pendulum.from_format(email_message['Date'], 'ddd, DD MMM YYYY HH:mm:ss Z')

        # Update the fields on the Message
        message.history_id = response['historyId']
        message.thread_id = response['threadId']
        message.label_ids = response.get('labelIds', [])
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

        # Commit our message and create a Thread if we don't already have one
        with Session(db_engine) as session:
            session.add(message)

            try:
                statement = select(Thread).where(Thread.id == response['threadId'])
                thread = session.exec(statement).one()
            except NoResultFound:
                thread = Thread(id=response['threadId'], mailbox_id=self.id)
                session.add(thread)

            session.commit()

            # If the message's thread needs to be processed, schedule it
            if not message.thread.processed:
                from .tasks import process_inbox_thread
                task_manager.add_task(
                    task=process_inbox_thread,
                    thread_id=message.thread_id
                )

            # And if the message hasn't been processed, generate an embedding for it
            if not message.processed:
                from .tasks import generate_embedding_for_message
                task_manager.add_task(
                    task=generate_embedding_for_message,
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

    def get_messages(self):
        """Get all the messages in the mailbox."""
        with Session(db_engine) as session:
            messages = session.exec(
                select(Message).where(Message.mailbox_id == self.id)
            ).all()

        mailbox_data = {}
        for message in messages:
            mailbox_data[message.thread_id] = {
                'id': message.id,
                'message_type': message.message_type,
                'summary': message.summary,
                'selected_functions': message.selected_functions,
                'executed_functions': message.executed_functions,
            }
        return mailbox_data

    def search_embeddings(self, query: str, k: int = 10):
        """Search the mailbox's embeddings for a query."""
        # Generate an embedding for the query
        query_embedding = generate_embedding(query)
        serialized_query_embedding = serialize_float32(query_embedding)

        # Run the query against the VecMessage table to find the 10 most similar messages
        with Session(db_engine) as session:
            results = session.exec(text(
                'select * from vec_message where body_embedding match :query_embedding limit :k'
            ).bindparams(
                query_embedding=serialized_query_embedding,
                k=k
            )).all()

            # Get the message_ids from the results
            message_ids = [message_id for message_id, embedding in results]

            # Get the messages from the Message table
            messages = session.exec(select(Message).where(Message.id.in_(message_ids))).all()

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

class Thread(SQLModel, table=True):
    id: str | None = SQLModelField(default=None, primary_key=True)

    mailbox_id: int = SQLModelField(default=None, foreign_key='mailbox.id')
    mailbox: "Mailbox" = Relationship(back_populates='threads')

    messages: list['Message'] = Relationship(
        back_populates='thread',
        cascade_delete=True,
        sa_relationship_kwargs={
            'lazy': 'subquery',
            'order_by': 'desc(Message.received_at)'
        }
    )

    category: ThreadCategory | None = SQLModelField(default=None, sa_column=Column(Enum(ThreadCategory)))
    summary: str | None = None

    functions_analyzed: bool = SQLModelField(default=False)
    selected_functions: dict[str, SelectedFunction] = SQLModelField(default_factory=dict, sa_column=Column(JSON))
    executed_functions: dict[str, ExecutedFunction] = SQLModelField(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = SQLModelField(default_factory=datetime.now)

    @property
    def in_inbox(self):
        """Returns True if the thread has a message in the user's inbox."""
        return any(message.in_inbox for message in self.messages)

    @property
    def processed(self):
        """
        Returns True if the thread has been processed, according to the criteria below:

        If the message is not in the user's inbox, then it needs no processing.

        Otherwise, the message needs to have a category, summary, and functions
        analyzed.
        """
        if not self.in_inbox:
            return True

        return self.category is not None and self.summary is not None and self.functions_analyzed

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
        """Analyze and process the thread."""
        self.set_category()
        self.generate_summary()
        self.select_functions()

    def set_category(self):
        """Categorize the thread based on its contents."""
        # If we already have a category, do nothing
        if self.category is not None:
            return

        prompt_template = """
        <context>
        {{ thread_details }}
        {{ general_context }}
        </context>

        <instructions>
        {{ instructions }}

        {% for category, description in category_descriptions.items() %}
        "{{ category.value }}": {{ description }}
        {% endfor %}
        </instructions>
        """

        partial_variables = {
            'instructions': 'Categorize this email thread into one of the categories listed below. When deciding between multiple categories, choose the one that best fits the most recently received message. If no category fits well, use the "Miscellaneous" category.',
            'category_descriptions': THREAD_CATEGORY_DESCRIPTIONS
        }

        class CategorizeThread(BaseModel):
            category: ThreadCategory

        input_variables = {
            'general_context': self.mailbox.get_general_context(),
            'thread_details': self.get_details()
        }

        result = generate_completion_with_validation(
            prompt_template=prompt_template,
            partial_variables=partial_variables,
            input_variables=input_variables,
            output_model=CategorizeThread,
            llm_temperature=0
        )

        self.category = result.category

    def generate_summary(self):
        """Generate a summary for the thread."""
        # If we already have a summary, do nothing
        if self.summary is not None:
            return

        prompt_template = """
        <context>
        {{ thread_details }}
        {{ general_context }}
        </context>

        <instructions>
        {{ instructions }}
        </instructions>
        """

        partial_variables = {
            'instructions': 'Summarize this email thread into one phrase of maximum 80 characters. Focus on the main point of the thread and any actionable items for the user. In threads with many messages, focus on the most recent messages.'
        }

        class ThreadSummary(BaseModel):
            summary: str = Field(max_length=80)

        input_variables = {
            'general_context': self.mailbox.get_general_context(),
            'thread_details': self.get_details()
        }

        result = generate_completion_with_validation(
            prompt_template=prompt_template,
            partial_variables=partial_variables,
            input_variables=input_variables,
            output_model=ThreadSummary
        )

        self.summary = result.summary

    def select_functions(self):
        """Analyzes this thread vs. the library of available Speck functions and selects the most relevant ones, if any, to surface to the user."""
        # If we already have selected functions, do nothing
        if self.functions_analyzed:
            return

        prompt_template = """
        <context>
        {{ thread_details }}
        <speck-library>
        {% for func_name, func_details in speck_library.functions.items() %}
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
        </speck-library>
        {{ general_context }}
        </context>

        <instructions>
        {{ instructions }}
        </instructions>
        """

        partial_variables = {
            'instructions': "Speck Functions are actions that an AI assistant can perform on behalf of the user. Based on the contents of the email the user received, determine which Speck Functions, if any, are relevant to the message. If a function is relevant, identify which function, the arguments it should use based on the message, the text the UI button should display, and the reason for the function's relevance to this email message. Most of the time, no Speck Functions will be relevant, and so you should set the 'no_functions_selected' field to true. Do not invent new functions, only return functions that are already in the Speck library.",
            'speck_library': speck_library
        }

        class SelectedFunctions(BaseModel):
            no_functions_selected: bool = Field(default=True)
            functions: Optional[List[SelectedFunction]] = None

        input_variables = {
            'general_context': self.mailbox.get_general_context(),
            'thread_details': self.get_details()
        }

        result = generate_completion_with_validation(
            prompt_template=prompt_template,
            partial_variables=partial_variables,
            input_variables=input_variables,
            output_model=SelectedFunctions,
            llm_temperature=0
        )

        if result.functions is not None:
            self.selected_functions = {func.name: func.model_dump_json() for func in result.functions}
        self.functions_analyzed = True


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

class Message(SQLModel, table=True):
    id: str | None = SQLModelField(default=None, primary_key=True)

    mailbox_id: int = SQLModelField(default=None, foreign_key='mailbox.id', ondelete='CASCADE')
    mailbox: "Mailbox" = Relationship(back_populates='messages')

    raw: str
    history_id: int

    thread_id: str = SQLModelField(default=None, foreign_key='thread.id', ondelete='CASCADE')
    thread: "Thread" = Relationship(back_populates='messages')

    label_ids: List[str] = SQLModelField(default_factory=list, sa_column=Column(JSON))

    from_: str
    to: List[str] = SQLModelField(default_factory=list, sa_column=Column(JSON))
    cc: List[str] = SQLModelField(default_factory=list, sa_column=Column(JSON))
    bcc: List[str] = SQLModelField(default_factory=list, sa_column=Column(JSON))
    subject: str
    received_at: datetime
    body: str

    embedding_generated: bool = SQLModelField(default=False)

    created_at: datetime = SQLModelField(default_factory=datetime.now)

    @property
    def in_inbox(self):
        """Returns True if the message is in the user's inbox."""
        return 'INBOX' in self.label_ids

    @property
    def processed(self):
        """
        Returns True if the message has had its embedding generated.
        """
        return self.embedding_generated

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
        # Check if we already have an embedding
        with Session(db_engine) as session:
            try:
                session.exec(select(VecMessage).where(VecMessage.message_id == self.id)).one()

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

class VecMessage(SQLModel, table=True):
    """
    A virtual table that stores the embeddings of the messages.

    NOTE: This is a virtual table that is created using the sqlite-vec extension,
    not by SQLModel.
    """
    message_id: str | None = SQLModelField(default=None, primary_key=True)

    body_embedding: bytes = SQLModelField(sa_column=Column(BLOB))

    @declared_attr
    def __tablename__(cls) -> str:
        return 'vec_message'
