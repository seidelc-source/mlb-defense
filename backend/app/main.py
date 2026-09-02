from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
