import base64
from datetime import datetime
import enum
import email
import html2text
import pendulum
from pydantic import BaseModel, Field
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.exc import NoResultFound
from sqlmodel import Column, Enum, Field, Session, SQLModel, Relationship, select, delete
from typing import List

from config import db_engine, task_manager, template_env
from core.utils import run_llamafile_completion

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
                # If we have a Message record for this message_id, then we don't
                # need to create a new one
                try:
                    statement = select(
                        Message
                    ).where(
                        Message.id == message_id,
                        Message.mailbox_id == self.id
                    )
                    message = session.exec(statement).one()

                    # If the message is still missing a type or a summary, then
                    # we need to process it
                    if not message.processed:
                        from .tasks import process_new_message
                        task_manager.add_task(
                            priority=3,
                            task=process_new_message,
                            message_id=message_id
                        )

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

                content = email_message.get_body(preferencelist=('html', 'text')).get_content()
                message.body = text_maker.handle(content)

                session.add(message)

            # Update the Mailbox's last_synced_at
            self.last_synced_at = last_synced_at
            session.add(self)

            # Delete old Message objects for emails that are no longer in the inbox
            session.exec(delete(Message).where(Message.id.not_in(message_ids)))

            # Generate summaries for new messages
            for message_id in new_message_ids:
                from .tasks import process_new_message
                task_manager.add_task(
                    priority=3,
                    task=process_new_message,
                    message_id=message_id
                )

            session.commit()

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

        print(f"Inserted message with ID: {response['id']}")


class ActionNecessity(str, enum.Enum):
    NONE = 'None'
    OPTIONAL = 'Optional'
    RECOMMENDED = 'Recommended'
    REQUIRED = 'Required'

ACTION_NECESSITY_DESCRIPTIONS = {
    ActionNecessity.NONE: "No action needed.",
    ActionNecessity.OPTIONAL: "Action is not necessary, but the user may choose to take action based on their current needs and the contents of the email.",
    ActionNecessity.RECOMMENDED: "Action not necessary, but taking no action may result in negative consequences.",
    ActionNecessity.REQUIRED: "At least one action is required to avoid negative consequences."
}

class ActionUrgency(str, enum.Enum):
    IMMEDIATE = 'Immediate'
    HIGH = 'High'
    MEDIUM = 'Medium'
    LOW = 'Low'

ACTION_URGENCY_DESCRIPTIONS = {
    ActionUrgency.IMMEDIATE: "Action needed ASAP to avoid negative consequences.",
    ActionUrgency.HIGH: "Action needed within 24 hours to avoid negative consequences.",
    ActionUrgency.MEDIUM: "Action needed within a week to avoid negative consequences.",
    ActionUrgency.LOW: "Action needed, but not urgently and may not have any time constraints at all.",
}

class MessageAction(BaseModel):
    action: str
    necessity: ActionNecessity
    urgency: ActionUrgency

class MessageType(str, enum.Enum):
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

MESSAGE_TYPE_DESCRIPTIONS = {
    MessageType.CORRESPONDENCE: "Emails from individuals, including personal and professional communications.",
    MessageType.PROFESSIONAL_OPPORTUNITIES: "Job opportunities, application statuses, career opportunities, and professional networking emails.",
    MessageType.RECEIPTS: "Purchase confirmations, order receipts, and transaction details.",
    MessageType.BILLS_AND_STATEMENTS: "Utility bills, credit card statements, bank statements, and loan notices.",
    MessageType.PROMOTIONS_AND_DEALS: "Promotional emails, discount offers, coupons, and sales alerts.",
    MessageType.NEWSLETTERS: "Regular email updates from subscribed newsletters, blogs, and websites.",
    MessageType.UPDATES: "Updates from services or products, software updates, and feature announcements.",
    MessageType.ORDER_CONFIRMATIONS: "Order confirmations and shipping notifications from online purchases.",
    MessageType.PRODUCT_RECOMMENDATIONS: "Emails recommending products based on previous purchases or browsing history.",
    MessageType.TICKETS_AND_BOOKINGS: "Travel itineraries, flight confirmations, hotel bookings, concert tickets, sports events, theater tickets, and event invitations.",
    MessageType.COURSES_AND_LEARNING: "Online course updates, class schedules, and educational content.",
    MessageType.ORGANIZATIONAL_ANNOUNCEMENTS: "Emails from educational institutions, company-wide emails from employers, and announcements from non-professional organizations.",
    MessageType.UTILITIES_AND_SERVICES: "Notifications from utility providers, service updates, maintenance notices, internet, cable, phone providers, and other service companies.",
    MessageType.SECURITY_ALERTS: "Account security notifications, password resets, and suspicious activity alerts.",
    MessageType.SERVICE_NOTIFICATIONS: "Notifications from apps and services, error messages, and system alerts.",
    MessageType.SURVEYS_AND_FEEDBACK: "Requests for feedback, surveys, and user experience questionnaires.",
    MessageType.POLITICAL: "Political emails, including donation requests and campaign updates.",
    MessageType.SPAM: "Unwanted emails, phishing attempts, and known spam.",
    MessageType.HEALTH_AND_WELLNESS: "Emails from healthcare providers, appointment reminders, and health-related updates.",
    MessageType.MISCELLANEOUS: "An email which does not fit any other category."
}

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

    message_type: MessageType | None = Field(default=None, sa_column=Column(Enum(MessageType)))
    actions: List[MessageAction] = Field(default_factory=list, sa_column=Column(JSON))
    action_necessary: ActionNecessity | None = Field(default=None, sa_column=Column(Enum(ActionNecessity)))
    action_urgency: ActionUrgency | None = Field(default=None, sa_column=Column(Enum(ActionUrgency)))
    summary: str | None = None

    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def processed(self):
        return self.message_type is not None and self.summary is not None and self.action_necessary is not None

    def analyze_and_process(self):
        """Analyze a new message and process it."""
        self.set_type()
        self.generate_summary()
        self.analyze_actions_and_urgency()

    def set_type(self):
        """Categorize the message based on its contents."""
        # If we already have a type, do nothing
        if self.message_type is not None:
            return

        class CategorizeMessageType(BaseModel):
            type: MessageType

        prompt = template_env.get_template('message_type_prompt.txt').render(
            message=self,
            instructions='Categorize this email message into one of the categories listed below. If no category fits best, use the "Miscellaneous" category.',
            message_type_descriptions=MESSAGE_TYPE_DESCRIPTIONS
        )
        result = run_llamafile_completion(
            prompt=prompt,
            model=CategorizeMessageType
        )

        self.message_type = result.type

    def generate_summary(self):
        """Generate and store a short summary of the message."""
        # If we already have a summary, do nothing
        if self.summary is not None:
            return

        class MessageSummary(BaseModel):
            summary: str = Field(max_length=80)

        prompt = template_env.get_template('message_summary_prompt.txt').render(
            message=self,
            instructions='Summarize this email into one phrase of maximum 80 characters. Focus on the main point of the message and any actionable items for the user.',
        )
        result = run_llamafile_completion(
            prompt=prompt,
            model=MessageSummary
        )

        self.summary = result.summary

    def analyze_actions_and_urgency(self):
        """
        Analyze the message, determine if any actions are required, and
        determine the urgency of any actions identified.
        """
        # TODO: Disabling for now
        self.action_necessary = ActionNecessity.NONE
        self.action_urgency = None
        self.actions = []
        return

        # If we already have an action_necessary value, do nothing
        if self.action_necessary is not None:
            return

        class AnalyzeRequiredActions(BaseModel):
            actions: List[MessageAction] = Field(default_factory=list)

        prompt = template_env.get_template('analyze_actions_and_urgency_prompt.txt').render(
            message=self,
            instructions='Based on the contents of the email, determine if any action is required from the user, erring on the side of minimal or no action. If action is required, identify the minimum specific task for the user and add each one to the "actions" array. For each action entry, include a "necessity" field and an "urgency" field, using the values provided.',
            action_necessity_descriptions=ACTION_NECESSITY_DESCRIPTIONS,
            action_urgency_descriptions=ACTION_URGENCY_DESCRIPTIONS
        )
        result = run_llamafile_completion(
            prompt=prompt,
            model=AnalyzeRequiredActions
        )

        # If no actions are found, set action_necessary to NONE and action_urgency to None
        if not result.actions:
            self.actions = []
            self.action_necessary = ActionNecessity.NONE
            self.action_urgency = None
            return

        # Define priority order for ActionNecessity and ActionUrgency
        necessity_priority = {
            ActionNecessity.NONE: 0,
            ActionNecessity.OPTIONAL: 1,
            ActionNecessity.RECOMMENDED: 2,
            ActionNecessity.REQUIRED: 3
        }
        urgency_priority = {
            ActionUrgency.LOW: 0,
            ActionUrgency.MEDIUM: 1,
            ActionUrgency.HIGH: 2,
            ActionUrgency.IMMEDIATE: 3
        }

        # Find the most necessary action, breaking ties with urgency
        most_necessary_action = max(
            result.actions,
            key=lambda action: (necessity_priority[action.necessity], urgency_priority[action.urgency])
        )

        # Set the action_necessary and action_urgency based on the most necessary action
        self.action_necessary = most_necessary_action.necessity
        self.action_urgency = most_necessary_action.urgency
        self.actions = [action.model_dump_json() for action in result.actions]
