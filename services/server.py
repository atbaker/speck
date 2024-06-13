from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def hello_world():
    return {"output": "Hello from Python!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7725)
