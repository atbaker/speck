from fastapi import FastAPI
from sqlmodel import SQLModel

from config import engine
from emails import models
from emails import routes as email_routes
from setup import routes as setup_routes


app = FastAPI()

app.include_router(email_routes.router)
app.include_router(setup_routes.router)

# Create the database tables
SQLModel.metadata.create_all(engine)

@app.get("/")
async def hello_world():
    return {"output": "Hello, world!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7725)
