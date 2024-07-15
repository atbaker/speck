from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel

from emails import models
from emails import routes as email_routes
from config import db_engine, task_manager
from core import routes as core_routes
from core.llm_service_manager import llm_service_manager
from core.tasks import set_up_llm_service
from emails.tasks import sync_inbox


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for the app."""
    # Create the database tables
    SQLModel.metadata.create_all(db_engine)

    # Start the background task manager
    task_manager.start(num_workers=1)

    # Add a recurring task to sync the inbox every minute
    task_manager.add_recurring_task(
        interval=60,
        priority=2,
        task=sync_inbox
    )

    # Schedule a task to set up the LLM server
    task_manager.add_task(
        priority=1,
        task=set_up_llm_service
    )

    # Allow FastAPI to start up
    yield

    # Force stop the LLM service before shutdown
    llm_service_manager.force_stop_server()

    # Stop the background task manager
    task_manager.stop()


app = FastAPI(lifespan=lifespan)

app.include_router(email_routes.router)
app.include_router(core_routes.router)


@app.get("/")
async def hello_world():
    return {"output": "Hello, world!"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7725)
