from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.core.database import engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.redis import close_redis
from app.models.base import Base
from app.routers.players import router as players_router
from app.routers.routers import (
    alignment_router,
    ingest_router,
    range_router,
    spray_router,
    stadium_router,
    team_router,
    weather_router,
)
from app.workers.scheduler import start_scheduler, stop_scheduler

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — allow the Vite dev server in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


# Public mode (e.g. Cloudflare tunnel): visitors read + compute, never mutate.
# Checked per-request via get_settings() so tests can toggle the cached object.
_LOCKED_PREFIXES = ("/api/v1/ingest",)
_LOCKED_PATTERNS = ("/injury",)  # POST/PUT injury add + heal


@app.middleware("http")
async def public_mode_guard(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS") and get_settings().public_mode:
        path = request.url.path
        if path.startswith(_LOCKED_PREFIXES) or any(p in path for p in _LOCKED_PATTERNS):
            return JSONResponse(
                status_code=403,
                content={"detail": "Read-only public deployment — this action is disabled."},
            )
    return await call_next(request)


# Mount all routers under /api/v1
PREFIX = "/api/v1"
app.include_router(players_router, prefix=PREFIX)
app.include_router(spray_router, prefix=PREFIX)
app.include_router(alignment_router, prefix=PREFIX)
app.include_router(range_router, prefix=PREFIX)
app.include_router(weather_router, prefix=PREFIX)
app.include_router(stadium_router, prefix=PREFIX)
app.include_router(team_router, prefix=PREFIX)
app.include_router(ingest_router, prefix=PREFIX)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# ── Built frontend (single-origin serving for local/tunnel deployment) ───────
# When frontend/dist exists (built with VITE_API_BASE_URL=/api/v1), serve the
# SPA from this process: one origin, one port, no CORS — a Cloudflare tunnel
# to :8000 exposes the whole app. Routers above win over the catch-all.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIST / full_path
        if full_path and ".." not in full_path and candidate.is_file():
            return FileResponse(candidate)
        # client-side routes (/spray, /players, ...) fall back to the SPA shell
        return FileResponse(FRONTEND_DIST / "index.html")
