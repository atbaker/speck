from typing import Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool, ToolException

from pydantic import BaseModel, Field
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select

from config import db_engine
from .models import Mailbox, Message


class CalculatorInput(BaseModel):
    a: int = Field(description="first number")
    b: int = Field(description="second number")


class CustomCalculatorTool(BaseTool):
    name: str = "Calculator"
    description: str = "A very simple calculator. Input two numbers and get the result of their addition."
    args_schema: Type[BaseModel] = CalculatorInput
    return_direct: bool = True

    def _run(
        self, a: int, b: int, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        return {
            'output': a + b
        }
    

class RecentEmailsInput(BaseModel):
    limit: int = Field(description="The number of recent emails to retrieve")


class RecentEmailsTool(BaseTool):
    name: str = "RecentEmails"
    description: str = "Get the most recently received emails from the user's Gmail mailbox. Limit the number of emails to the specified number."
    args_schema: Type[BaseModel] = RecentEmailsInput

    def _run(
        self, limit: int, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        with Session(db_engine) as session:
            try:
                mailbox = session.exec(select(Mailbox)).one()
            except NoResultFound:
                # If we didn't find a Mailbox, then return an error
                raise ToolException('No mailbox found')
            
            messages = session.exec(select(Message).where(Message.mailbox_id == mailbox.id).order_by(Message.created_at.desc()).limit(limit)).all()

        return {
            'output': messages
        }

