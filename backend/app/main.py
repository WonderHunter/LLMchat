import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.config import get_settings
from app.db import init_db
from app.routers import auth, keys, models
from app.services.catalog import catalog


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    refresh_minutes = get_settings().catalog_refresh_minutes
    refresher = (
        asyncio.create_task(catalog.run_forever(refresh_minutes)) if refresh_minutes > 0 else None
    )
    yield
    if refresher:
        refresher.cancel()
        with suppress(asyncio.CancelledError):
            await refresher


app = FastAPI(title="LLMchat", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(models.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
