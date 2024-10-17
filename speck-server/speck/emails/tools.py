from typing import Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool, ToolException
import logging

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound

from config import db_engine
from .models import Mailbox

logger = logging.getLogger(__name__)


class ListThreadsInput(BaseModel):
    max_results: int = Field(default=10, ge=5, le=25, description="The maximum number of threads to retrieve, up to `25`. Defaults to `10`.")


class ListThreadsTool(BaseTool):
    name: str = "ListThreads"
    description: str = "List the threads in the user's Gmail mailbox. Returned in descending order, with the most recently received / updated threads first."
    args_schema: Type[BaseModel] = ListThreadsInput

    def _run(
        self, max_results: int = 10, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        with Session(db_engine) as session:
            try:
                mailbox = session.execute(select(Mailbox)).scalar_one()
            except NoResultFound:
                # If we didn't find a Mailbox, then return an error
                raise ToolException('No mailbox found')
            
        threads = mailbox.list_threads(
            max_results=max_results
        )

        results = [thread.get_details(include_body=True) for thread in threads]

        return {
            'num_threads': len(results),
            'output': results
        }


class SearchThreadsInput(BaseModel):
    query: str = Field(description="A search query to filter the user's email threads. Enclose a phrase in quotes to match it exactly.")
    max_results: int = Field(default=10, ge=5, le=25, description="The maximum number of threads to retrieve, up to `25`.")

class SearchThreadsTool(BaseTool):
    name: str = "SearchThreads"
    description: str = "Search the threads in the user's Gmail mailbox. Uses a combination of full text search and semantic search, returning results in a Reciprocal Rank Fusion (RRF) ranking."
    args_schema: Type[BaseModel] = SearchThreadsInput

    def _run(
        self, query: str, max_results: int = 10, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        with Session(db_engine) as session:
            try:
                mailbox = session.execute(select(Mailbox)).scalar_one()
            except NoResultFound:
                # If we didn't find a Mailbox, then return an error
                raise ToolException('No mailbox found')

            threads = mailbox.search(
                query=query,
                max_results=max_results
            )

            results = [thread.get_details(include_body=True) for thread in threads]

        return {
            'num_threads': len(results),
            'output': results
        }


class GetThreadInput(BaseModel):
    thread_id: str = Field(description="The ID of the thread to retrieve.", max_length=16)


class GetThreadTool(BaseTool):
    name: str = "GetThread"
    description: str = "Get the details of a thread in the user's Gmail mailbox."
    args_schema: Type[BaseModel] = GetThreadInput

    def _run(
        self, thread_id: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        with Session(db_engine) as session:
            try:
                mailbox = session.execute(select(Mailbox)).scalar_one()
            except NoResultFound:
                # If we didn't find a Mailbox, then return an error
                raise ToolException('No mailbox found')

            thread = mailbox.get_thread(thread_id)

        return {
            'output': thread.get_details(include_body=True, as_string=True)
        }
