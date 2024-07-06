from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel

from emails import models
from emails import routes as email_routes
from config import cache, db_engine
from core import routes as core_routes
from core.llm_service_manager import llm_service_manager
from core.tasks import set_up_llm_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for the app."""
    # Schedule a task to set up the LLM server
    set_up_llm_service.delay()

    # Create the database tables
    SQLModel.metadata.create_all(db_engine)

    # Clear the cache
    cache.clear()

    # Allow FastAPI to start up
    yield

    # Force stop the LLM service before shutdown
    llm_service_manager.force_stop_server()


app = FastAPI(lifespan=lifespan)

app.include_router(email_routes.router)
app.include_router(core_routes.router)


@app.get("/")
async def hello_world():
    return {"output": "Hello, world!"}
