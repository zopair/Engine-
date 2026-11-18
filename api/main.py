from fastapi import FastAPI

from api.routes_chat import router as chat_router
from memory.database import database

app = FastAPI(title="Autonomous AI Engine", version="0.1.0")

@app.on_event("startup")
async def startup() -> None:
    database.initialize()

app.include_router(chat_router)
