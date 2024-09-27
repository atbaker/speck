from typing import Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool, ToolException

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound

from config import db_engine
from .models import Mailbox


class ListThreadsInput(BaseModel):
    include_body: Optional[bool] = Field(default=False, description="If true, the full body of each message will be included in the output")
    max_results: int = Field(default=5, ge=1, le=100, description="The maximum number of threads to retrieve, up to 100")


class ListThreadsTool(BaseTool):
    name: str = "ListThreads"
    description: str = "List threads in the user's Gmail mailbox, filtered by the specified criteria. Threads are returned in descending order based on the date they were last updated."
    args_schema: Type[BaseModel] = ListThreadsInput

    def _run(
        self, include_body: bool, max_results: int, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        with Session(db_engine) as session:
            try:
                mailbox = session.execute(select(Mailbox)).scalar_one()
            except NoResultFound:
                # If we didn't find a Mailbox, then return an error
                raise ToolException('No mailbox found')
            
            threads = mailbox.list_threads(max_results=max_results)

        results = []
        for thread in threads:
            results.append({
                'id': thread.id,
                'category': thread.category,
                'summary': thread.summary,
                'messages': [
                    {
                        'id': message.id,
                        'label_ids': message.label_ids,
                        'from': message.from_,
                        'to': message.to,
                        'cc': message.cc,
                        'bcc': message.bcc,
                        'subject': message.subject,
                        'received_at': message.received_at,
                        'body': message.body if include_body else None
                    }
                    for message in thread.messages
                ]
            })

        return {
            'output': results
        }
