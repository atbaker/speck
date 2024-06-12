from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/")
async def hello_world():
    return {"output": "Hello from Python!"}

if __name__ == "__main__":
    import uvicorn

    socket_path = "/tmp/fastapi.sock"
    if os.path.exists(socket_path):
        os.remove(socket_path)

    uvicorn.run(app, uds=socket_path)
