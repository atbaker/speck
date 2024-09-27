from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, Mapped, mapped_column, relationship
from sqlalchemy import select, Integer, JSON, String, ForeignKey, DateTime

from config import db_engine
from core.models import Base
from core.utils import generate_completion_with_validation
from emails.models import Mailbox, Message


PROFILE_ATTRIBUTE_PROMPT_TEMPLATE = """
    <context>
    {{ general_context }}
    <messages>
    {% for message in message_details %}
        {{ message }}
    {% endfor %}
    </messages>
    </context>

    <instructions>
    {{ instructions }}
    </instructions>
    """

class Profile(Base):
    __tablename__ = 'profiles'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[Optional[str]] = mapped_column(String(80))
    primary_address: Mapped[Optional[str]] = mapped_column(String(160))
    financial_institutions: Mapped[List[str]] = mapped_column(JSON)

    mailbox_id: Mapped[int] = mapped_column(ForeignKey("mailboxes.id"), unique=True)
    mailbox: Mapped["Mailbox"] = relationship()

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def complete(self):
        """
        Whether the Profile is complete.
        """
        return self.name is not None and self.primary_address is not None and len(self.financial_institutions) > 0

    def get_profile_context(self):
        """
        Get the profile context.
        """
        return {
            'full_name': self.name,
            'primary_address': self.primary_address
        }

    def update(self):
        """
        Update the Profile's attributes.
        """
        if not self.name:
            self.determine_name()
        if not self.primary_address:
            self.determine_primary_address()
        if not self.financial_institutions:
            self.determine_financial_institutions()

    def determine_name(self):
        """
        Uses the mailbox's 10 most recent messages to determine the user's name.
        """
        # If we already have a name, do nothing
        if self.name is not None:
            return

        partial_variables = {
            'instructions': "Based on the user's email address and the the contents of these 10 recent email messages from the user's inbox, determine the user's full name."
        }

        class FullName(BaseModel):
            full_name: str = Field(max_length=80)

        # Get the 10 most recent messages
        with Session(db_engine) as session: 
            messages = session.execute(
                select(Message).where(Message.mailbox_id == self.mailbox_id).order_by(Message.received_at.desc()).limit(10)
            ).scalars().all()

        input_variables = {
            'general_context': self.mailbox.get_general_context(),
            'message_details': [message.get_details() for message in messages]
        }

        result = generate_completion_with_validation(
            prompt_template=PROFILE_ATTRIBUTE_PROMPT_TEMPLATE,
            partial_variables=partial_variables,
            input_variables=input_variables,
            output_model=FullName,
            llm_temperature=0
        )

        self.name = result.full_name

    def determine_primary_address(self):
        """
        Uses the mailbox's 10 most relevant "order confirmation" messages to determine the user's primary physical address.
        """
        # If we already have a primary address, do nothing
        if self.primary_address is not None:
            return
        
        partial_variables = {
            'instructions': "Based on the contents of these 10 recent order confirmation messages from the user's inbox, determine the user's primary physical address. Example output: '123 Main St, Anytown, CA 12345'.",
        }

        class PrimaryAddress(BaseModel):
            primary_address: str = Field(max_length=160)

        # Get the 10 messages from the user's mailbox which are 'order confirmation' messages
        order_confirmation_messages = self.mailbox.search_embeddings('order confirmation', k=10)

        input_variables = {
            'general_context': self.mailbox.get_general_context(),
            'message_details': [message.get_details() for message in order_confirmation_messages]
        }

        result = generate_completion_with_validation(
            prompt_template=PROFILE_ATTRIBUTE_PROMPT_TEMPLATE,
            partial_variables=partial_variables,
            input_variables=input_variables,
            output_model=PrimaryAddress,
            llm_temperature=0
        )

        self.primary_address = result.primary_address

    def determine_financial_institutions(self):
        """
        Uses the mailbox's 10 most recent messages to determine the list of
        financial institutions the user has accounts with.
        """
        # If we already have financial institutions, do nothing
        if len(self.financial_institutions) > 0:
            return
        
        partial_variables = {
            'instructions': "Based on the contents of these 10 recent banking messages from the user's inbox, determine the list of financial institutions the user has accounts with. Include each institution only once. Do not include credit bureaus like TransUnion, Equifax, or Experian. Example output: [\"Bank of America\", \"Chase\", \"Wells Fargo\"].",
        }

        class FinancialInstitutions(BaseModel):
            financial_institutions: List[str] = Field(max_length=80)

        # Get the 10 messages from the user's mailbox which are 'banking' messages
        banking_messages = self.mailbox.search_embeddings('banking', k=10)

        input_variables = {
            'general_context': self.mailbox.get_general_context(),
            'message_details': [message.get_details() for message in banking_messages]
        }

        result = generate_completion_with_validation(
            prompt_template=PROFILE_ATTRIBUTE_PROMPT_TEMPLATE,
            partial_variables=partial_variables,
            input_variables=input_variables,
            output_model=FinancialInstitutions,
            llm_temperature=0
        )

        self.financial_institutions = result.financial_institutions