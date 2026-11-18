from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from api.routes_chat import router as chat_router
from memory.database import database


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    database.initialize()
    yield


app = FastAPI(
    title="Autonomous AI Engine",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(chat_router)
