from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright

from core import routes as core_routes
from emails import routes as email_routes


app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'https://mail.google.com',
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(email_routes.router)
app.include_router(core_routes.router)


@app.get("/")
async def hello_world():
    from core.cache import cache
    return {"output": f"Hello, world! Last task was {cache.get('last_task')}"}
