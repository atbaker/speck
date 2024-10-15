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
    include_body: Optional[bool] = Field(default=False, description="If `true`, the full body of each message will be included in the output. Defaults to `false`.")
    max_results: Optional[int] = Field(default=10, ge=1, le=100, description="The maximum number of threads to retrieve, up to 100. Defaults to `10`.")


class ListThreadsTool(BaseTool):
    name: str = "ListThreads"
    description: str = "List the threads in the user's Gmail mailbox. Returned in descending order, with the most recently received / updated threads first."
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
            
        threads = mailbox.list_threads(
            max_results=max_results
        )

        results = [thread.get_details(include_body=include_body) for thread in threads]

        return {
            'num_threads': len(results),
            'output': results
        }


class SearchThreadsInput(BaseModel):
    query: str = Field(default=None, description="A search query to filter the user's email threads.")
    include_body: Optional[bool] = Field(default=False, description="If `true`, the full body of each message will be included in the output. Defaults to `false`. If `true`, the `max_results` argument cannot exceed `5`.")
    max_results: Optional[int] = Field(default=10, ge=1, le=100, description="The maximum number of threads to retrieve, up to `100` (`5` if `include_body` is `true`).")

    @model_validator(mode='after')
    def check_max_results(cls, values):
        if values.include_body and values.max_results > 5:
            raise ValueError("If `include_body` is `true`, the `max_results` argument cannot exceed `5`.")
        return values

class SearchThreadsTool(BaseTool):
    name: str = "SearchThreads"
    description: str = "Search the threads in the user's Gmail mailbox. Uses a combination of full text search and semantic search, returning results in a Reciprocal Rank Fusion (RRF) ranking."
    args_schema: Type[BaseModel] = SearchThreadsInput

    def _run(
        self, query: str, include_body: bool, max_results: int, run_manager: Optional[CallbackManagerForToolRun] = None
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

            results = [thread.get_details(include_body=include_body) for thread in threads]

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
