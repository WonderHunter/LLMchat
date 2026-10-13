from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routers import auth


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="LLMchat", lifespan=lifespan)
app.include_router(auth.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
