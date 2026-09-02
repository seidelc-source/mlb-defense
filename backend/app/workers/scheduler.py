"""
Background job scheduler.
Started in FastAPI's lifespan context.  Each job is isolated — extractable
to a Celery task with minimal changes if the app needs to scale out.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()

scheduler = AsyncIOScheduler(timezone="UTC")


async def _run_statcast_ingest() -> None:
    """Nightly 02:00 UTC — pull yesterday's pitch data."""
    from app.services.ingest.statcast import StatcastIngestService

    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        svc = StatcastIngestService(session)
        count = await svc.ingest(yesterday, yesterday)
        await session.commit()
    logger.info("Nightly Statcast ingest complete: %d records", count)


async def _run_fielding_sync() -> None:
    """Weekly Sunday 04:00 UTC — sync OAA / FRV / sprint speed leaderboards."""
    from app.services.ingest.fielding import FieldingIngestService

    season = datetime.now(timezone.utc).year
    async with AsyncSessionLocal() as session:
        svc = FieldingIngestService(session)
        count = await svc.ingest(season)
        await session.commit()
    logger.info("Weekly fielding sync complete: %d records", count)


async def _run_spray_aggregate() -> None:
    """Nightly 03:30 UTC — aggregate PitchAppearance → BatterSprayProfile."""
    from app.services.ingest.spray_aggregate import SprayAggregateService

    season = datetime.now(timezone.utc).year
    async with AsyncSessionLocal() as session:
        svc = SprayAggregateService(session)
        count = await svc.aggregate(season)
        await session.commit()
    logger.info("Nightly spray aggregation complete: %d rows", count)


async def _run_pitcher_aggregate() -> None:
    """Nightly 03:45 UTC — aggregate PitchAppearance → PitcherProfile."""
    from app.services.ingest.pitcher_aggregate import PitcherAggregateService

    season = datetime.now(timezone.utc).year
    async with AsyncSessionLocal() as session:
        svc = PitcherAggregateService(session)
        count = await svc.aggregate(season)
        await session.commit()
    logger.info("Nightly pitcher aggregation complete: %d profiles", count)


async def _run_weather_fetch() -> None:
    """Hourly on game days — fetch game-time weather for today's games."""
    from app.services.weather_fetch import WeatherFetchService

    async with AsyncSessionLocal() as session:
        svc = WeatherFetchService(session)
        count = await svc.fetch_todays_games()
        await session.commit()
    logger.info("Hourly weather fetch complete: %d games updated", count)


def start_scheduler() -> None:
    if not settings.worker_enabled:
        logger.info("Workers disabled (WORKER_ENABLED=false)")
        return

    scheduler.add_job(_run_statcast_ingest, CronTrigger(hour=2, minute=0), id="statcast_nightly")
    scheduler.add_job(_run_fielding_sync, CronTrigger(day_of_week="sun", hour=4), id="fielding_weekly")
    scheduler.add_job(_run_spray_aggregate, CronTrigger(hour=3, minute=30), id="spray_aggregate")
    scheduler.add_job(_run_pitcher_aggregate, CronTrigger(hour=3, minute=45), id="pitcher_aggregate")
    scheduler.add_job(_run_weather_fetch, CronTrigger(minute=0), id="weather_hourly")

    scheduler.start()
    logger.info("APScheduler started with %d jobs", len(scheduler.get_jobs()))


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
