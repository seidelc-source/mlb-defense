"""
Backfill Statcast fielder-alignment columns (if_/of_fielding_alignment) onto
existing pitch_appearance rows — WITHOUT deleting/rebuilding them.

Why a dedicated script: StatcastIngestService.ingest() is delete-then-insert
per date window, so a plain re-ingest would rebuild ~700k rows/season and risks
data loss on a mid-pull failure. This script instead re-pulls Statcast and
issues idempotent UPDATEs keyed on mlb_play_id. Only batted-ball rows (bb_type
present) are updated — those are all the P0 eval harness needs.

Resumable & non-destructive:
  - Processes one calendar month at a time.
  - Skips a month whose batted-ball rows are already fully populated (unless
    --force), so an interrupted run can simply be re-invoked.
  - Never deletes; UPDATE is idempotent.

Usage:
    cd backend
    python -m scripts.backfill_alignment --season 2024
    python -m scripts.backfill_alignment --seasons 2021 2022 2023 2024
    python -m scripts.backfill_alignment --season 2024 --start 2024-04-01 --end 2024-04-30 --force
"""
from __future__ import annotations

import argparse
import asyncio
import calendar
import logging
from datetime import date

import pandas as pd
from sqlalchemy import bindparam, func, select, update

from app.core.database import AsyncSessionLocal
from app.models.pitch_appearance import PitchAppearance
import app.models  # noqa: F401 — register all mappers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("backfill_alignment")

# MLB regular season roughly spans late March → early October; pulling these
# months per season covers essentially all batted balls.
SEASON_MONTHS = (3, 4, 5, 6, 7, 8, 9, 10)


def _month_windows(season: int) -> list[tuple[str, str]]:
    windows = []
    for m in SEASON_MONTHS:
        last = calendar.monthrange(season, m)[1]
        windows.append((f"{season}-{m:02d}-01", f"{season}-{m:02d}-{last:02d}"))
    return windows


def _play_id(row) -> str:
    return f"{row.get('game_pk', '')}-{row.get('at_bat_number', '')}-{row.get('pitch_number', '')}"


async def _batted_ball_counts(session, start: date, end: date) -> tuple[int, int]:
    """(total batted-ball rows, rows already having if_fielding_alignment) in range."""
    total = await session.scalar(
        select(func.count())
        .select_from(PitchAppearance)
        .where(
            PitchAppearance.game_date >= start,
            PitchAppearance.game_date <= end,
            PitchAppearance.bb_type.is_not(None),
        )
    )
    covered = await session.scalar(
        select(func.count())
        .select_from(PitchAppearance)
        .where(
            PitchAppearance.game_date >= start,
            PitchAppearance.game_date <= end,
            PitchAppearance.bb_type.is_not(None),
            PitchAppearance.if_fielding_alignment.is_not(None),
        )
    )
    return int(total or 0), int(covered or 0)


async def _backfill_window(session, start: str, end: str, force: bool) -> int:
    import pybaseball

    s_date = date.fromisoformat(start)
    e_date = date.fromisoformat(end)

    total, covered = await _batted_ball_counts(session, s_date, e_date)
    if total == 0:
        logger.info("  %s → %s: no batted-ball rows in DB, skipping", start, end)
        return 0
    if covered >= total and not force:
        logger.info("  %s → %s: already covered (%d/%d), skipping", start, end, covered, total)
        return 0

    logger.info("  %s → %s: pulling Statcast (%d/%d covered)…", start, end, covered, total)
    loop = asyncio.get_event_loop()
    df: pd.DataFrame = await loop.run_in_executor(
        None, lambda: pybaseball.statcast(start_dt=start, end_dt=end)
    )
    if df is None or df.empty:
        logger.warning("  %s → %s: Statcast returned nothing", start, end)
        return 0

    # Only batted balls carry a fielding zone we score on; alignment is a
    # per-play attribute so restrict to reduce UPDATE volume.
    df = df[df["bb_type"].notna()]
    df = df.drop_duplicates(subset=["game_pk", "at_bat_number", "pitch_number"], keep="last")

    params = []
    for _, row in df.iterrows():
        iff = row.get("if_fielding_alignment")
        off = row.get("of_fielding_alignment")
        params.append(
            {
                "pid": _play_id(row),
                "iff": None if pd.isna(iff) else str(iff)[:20],
                "off": None if pd.isna(off) else str(off)[:20],
            }
        )
    if not params:
        return 0

    tbl = PitchAppearance.__table__
    stmt = (
        # Core UPDATE against the table (not the ORM entity) so executemany with
        # a per-row bindparam WHERE is supported.
        update(tbl)
        .where(tbl.c.mlb_play_id == bindparam("pid"))
        .values(
            if_fielding_alignment=bindparam("iff"),
            of_fielding_alignment=bindparam("off"),
        )
    )
    # Chunk the executemany to keep memory/statement size sane. (executemany
    # rowcount is unreliable, so we verify via a coverage recount below.)
    CHUNK = 5000
    for i in range(0, len(params), CHUNK):
        await session.execute(stmt, params[i : i + CHUNK])
        await session.flush()
    await session.commit()

    _, now_covered = await _batted_ball_counts(session, s_date, e_date)
    newly = now_covered - covered
    logger.info(
        "  %s → %s: pulled %d batted balls, coverage %d→%d (+%d)",
        start, end, len(params), covered, now_covered, newly,
    )
    return newly


async def backfill_season(season: int, start: str | None, end: str | None, force: bool) -> int:
    windows = [(start, end)] if start and end else _month_windows(season)
    total = 0
    async with AsyncSessionLocal() as session:
        logger.info("=== Backfilling alignment for season %d (%d windows) ===", season, len(windows))
        for w_start, w_end in windows:
            total += await _backfill_window(session, w_start, w_end, force)
    return total


async def main(seasons: list[int], start: str | None, end: str | None, force: bool) -> None:
    grand_total = 0
    for season in seasons:
        grand_total += await backfill_season(season, start, end, force)
    logger.info("Backfill complete: %d rows updated across %s", grand_total, seasons)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, help="Single season to backfill")
    parser.add_argument("--seasons", type=int, nargs="+", help="Multiple seasons")
    parser.add_argument("--start", type=str, help="Override window start (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="Override window end (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="Re-pull even if already covered")
    args = parser.parse_args()

    seasons = args.seasons or ([args.season] if args.season else [])
    if not seasons:
        parser.error("Provide --season or --seasons")
    asyncio.run(main(seasons, args.start, args.end, args.force))
