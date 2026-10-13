import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import ROOT_DIR, get_settings
from app.db import init_db
from app.routers import auth, chat, conversations, keys, models
from app.services.catalog import catalog

FRONTEND_DIST = (ROOT_DIR / "frontend" / "dist").resolve()


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
for module in (auth, keys, models, conversations, chat):
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str) -> FileResponse:
    """Sert l'interface compilée (pnpm build). En développement, c'est Vite qui s'en charge."""
    if path.startswith("api/") or not FRONTEND_DIST.is_dir():
        raise HTTPException(404, "Introuvable")
    target = (FRONTEND_DIST / path).resolve()
    if path and target.is_file() and target.is_relative_to(FRONTEND_DIST):
        return FileResponse(target)
    return FileResponse(FRONTEND_DIST / "index.html")
