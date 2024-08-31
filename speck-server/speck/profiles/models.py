from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLModelField, Relationship, Column, JSON, Session, select

from config import db_engine, template_env
from core.utils import generate_completion
from emails.models import Message


class Profile(SQLModel, table=True):
    id: int | None = SQLModelField(default=None, primary_key=True)

    name: Optional[str] = None
    primary_address: Optional[str] = None
    financial_institutions: List[str] = SQLModelField(default_factory=list, sa_column=Column(JSON))

    mailbox_id: int = SQLModelField(foreign_key="mailbox.id", unique=True)
    # mailbox: "Mailbox" = Relationship(back_populates="profile", sa_relationship_kwargs={"uselist": False})
    mailbox: "Mailbox" = Relationship(sa_relationship_kwargs={"uselist": False})

    created_at: datetime = SQLModelField(default_factory=datetime.now)

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
        
        # Get the 10 most recent messages # TODO: Increase this after switching to Llama 3.1
        with Session(db_engine) as session: 
            messages = session.exec(
                select(Message).where(Message.mailbox_id == self.mailbox_id).order_by(Message.received_at.desc()).limit(10)
            ).all()

        class FullName(BaseModel):
            full_name: str = Field(max_length=80)

        prompt = template_env.get_template('profile_attribute_prompt.txt').render(
            messages=messages,
            general_context=self.mailbox.get_general_context(),
            instructions="Based on the user's email address and the the contents of these 20 recent email messages from the user's inbox, determine the user's full name.",
        )

        result = generate_completion(
            prompt=prompt,
            return_model=FullName
        )

        self.name = result.full_name

    def determine_primary_address(self):
        """
        Uses the mailbox's 10 most relevant "order confirmation" messages to determine the user's primary physical address.
        """
        # If we already have a primary address, do nothing
        if self.primary_address is not None:
            return
        
        # Get the 10 messages from the user's mailbox which are 'order confirmation' messages
        order_confirmation_messages = self.mailbox.search_embeddings('order confirmation')

        class PrimaryAddress(BaseModel):
            primary_address: str = Field(max_length=160)

        prompt = template_env.get_template('profile_attribute_prompt.txt').render(
            messages=order_confirmation_messages,
            general_context=self.mailbox.get_general_context(),
            instructions="Based on the contents of these 10 recent order confirmation messages from the user's inbox, determine the user's primary physical address. Example output: '123 Main St, Anytown, CA 12345'.",
        )

        result = generate_completion(
            prompt=prompt,
            return_model=PrimaryAddress
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
        
        # Get the 10 messages from the user's mailbox which are 'banking' messages
        banking_messages = self.mailbox.search_embeddings('banking')

        class FinancialInstitutions(BaseModel):
            financial_institutions: List[str] = Field(max_length=80)

        prompt = template_env.get_template('profile_attribute_prompt.txt').render(
            messages=banking_messages,
            general_context=self.mailbox.get_general_context(),
            instructions="Based on the contents of these 10 recent banking messages from the user's inbox, determine the list of financial institutions the user has accounts with. Include each institution only once. Do not include credit bureaus like TransUnion, Equifax, or Experian. Example output: [\"Bank of America\", \"Chase\", \"Wells Fargo\"].",
        )

        result = generate_completion(
            prompt=prompt,
            return_model=FinancialInstitutions
        )

        self.financial_institutions = result.financial_institutions