from fastapi import FastAPI

from emails import models
from emails import routes as email_routes
from core import routes as core_routes


app = FastAPI()

app.include_router(email_routes.router)
app.include_router(core_routes.router)


@app.get("/")
async def hello_world():
    from core.cache import cache
    return {"output": f"Hello, world! Last task was {cache.get('last_task')}"}
