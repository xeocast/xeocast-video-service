from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


@app.get("/")
async def root():
    """Returns a welcome message."""
    return {"message": "Welcome to the FastAPI service!"}


@app.get("/health")
async def health_check():
    """Returns the health status of the service."""
    return {"status": "ok"}


class EchoRequest(BaseModel):
    message: str


@app.post("/echo")
async def echo(request: EchoRequest):
    """Echoes the received message back."""
    return {"echo": request.message} 