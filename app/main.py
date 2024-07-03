from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel

from config import cache, engine
from emails import models
from emails import routes as email_routes
from setup import routes as setup_routes
from app.setup.llm_service_manager import llm_service_manager
from setup.tasks import set_up_llm_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for the app."""
    # Schedule a task to set up the LLM server
    set_up_llm_service.delay()

    # Create the database tables
    SQLModel.metadata.create_all(engine)

    # Clear the cache
    cache.clear()

    # Allow FastAPI to start up
    yield

    # Force stop the LLM service before shutdown
    llm_service_manager.force_stop_server()


app = FastAPI(lifespan=lifespan)

app.include_router(email_routes.router)
app.include_router(setup_routes.router)


@app.get("/")
async def hello_world():
    return {"output": "Hello, world!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7725)
