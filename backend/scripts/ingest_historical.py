"""
Ingest multiple seasons of data (2016–2025) by calling ingest_all.main() for each.

Usage:
    cd backend
    python -m scripts.ingest_historical
    python -m scripts.ingest_historical --from-season 2020   # resume partway
    python -m scripts.ingest_historical --from-season 2025   # single season
"""
import argparse
import asyncio
import logging
import time

from scripts.ingest_all import main as ingest_season

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ingest_historical")

SEASONS = {
    2016: ("2016-04-03", "2016-10-02"),
    2017: ("2017-04-02", "2017-10-01"),
    2018: ("2018-03-29", "2018-10-01"),
    2019: ("2019-03-28", "2019-09-29"),
    2020: ("2020-07-23", "2020-09-27"),
    2021: ("2021-04-01", "2021-10-03"),
    2022: ("2022-04-07", "2022-10-05"),
    2023: ("2023-03-30", "2023-10-01"),
    2024: ("2024-03-28", "2024-09-29"),
    2025: ("2025-03-18", "2025-09-28"),  # 03-18 captures the Tokyo Series
}


async def run(from_season: int) -> None:
    for season, (start, end) in sorted(SEASONS.items()):
        if season < from_season:
            continue
        logger.info("========== SEASON %d (%s → %s) ==========", season, start, end)
        t0 = time.time()
        await ingest_season(season, start, end)
        elapsed = time.time() - t0
        logger.info("Season %d complete in %.1f minutes", season, elapsed / 60)

    logger.info("All historical seasons ingested.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-season", type=int, default=2016,
        help="Start from this season (skip earlier ones, useful for resuming)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.from_season))
