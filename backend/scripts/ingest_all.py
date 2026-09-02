"""
One-shot data bootstrap: players → statcast pitches → fielding profiles → spray aggregation.

Usage:
    cd backend
    python -m scripts.ingest_all --season 2024 --start 2024-06-01 --end 2024-06-14
"""
import argparse
import asyncio
import logging

from app.core.database import AsyncSessionLocal
import app.models  # noqa: F401 — register all mappers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("ingest_all")


async def main(
    season: int,
    start: str,
    end: str,
    skip_statcast: bool = False,
    statcast_only: bool = False,
) -> None:
    from app.services.ingest.ingest_services import (
        FieldingIngestService,
        PlayerIngestService,
        StatcastIngestService,
    )
    from app.services.ingest.pitcher_aggregate import PitcherAggregateService
    from app.services.ingest.spray_aggregate import SprayAggregateService

    if not statcast_only:
        async with AsyncSessionLocal() as session:
            logger.info("=== 1/5 Player rosters (season %d) ===", season)
            players = await PlayerIngestService(session).ingest(season)
            await session.commit()
            logger.info("Players: %d", players)

    if not skip_statcast:
        async with AsyncSessionLocal() as session:
            logger.info("=== 2/5 Statcast pitches %s → %s ===", start, end)
            pitches = await StatcastIngestService(session).ingest(start, end)
            await session.commit()
            logger.info("Pitches: %d", pitches)

    if statcast_only:
        logger.info("Statcast-only run complete.")
        return

    async with AsyncSessionLocal() as session:
        logger.info("=== 3/5 Fielding profiles (season %d) ===", season)
        profiles = await FieldingIngestService(session).ingest(season)
        await session.commit()
        logger.info("Fielding profiles: %d", profiles)

    async with AsyncSessionLocal() as session:
        logger.info("=== 4/5 Spray aggregation (season %d) ===", season)
        sprays = await SprayAggregateService(session).aggregate(season)
        await session.commit()
        logger.info("Spray rows: %d", sprays)

    async with AsyncSessionLocal() as session:
        logger.info("=== 5/5 Pitcher aggregation (season %d) ===", season)
        pitchers = await PitcherAggregateService(session).aggregate(season)
        await session.commit()
        logger.info("Pitcher profiles: %d", pitchers)

    logger.info("Bootstrap complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2024)
    parser.add_argument("--start", type=str, default="2024-06-01")
    parser.add_argument("--end", type=str, default="2024-06-14")
    parser.add_argument("--skip-statcast", action="store_true")
    parser.add_argument(
        "--statcast-only", action="store_true",
        help="Only ingest pitches for the date range (no rosters/fielding/spray)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.season, args.start, args.end, args.skip_statcast, args.statcast_only))
