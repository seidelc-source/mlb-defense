"""Backfill pitch_appearance.fielding_zone under the corrected hc frame.

Part of the coordinated frame rebuild (EXPERIMENTS.md 2026-09-04): recomputes
the 8-zone assignment for every pitch with hc coordinates using the canonical
era-aware transform, in chunks. Idempotent. Reports the fraction of zones that
changed (a pre-registered descriptive metric of the rebuild).

Usage:
    cd backend && python -m scripts.backfill_zones
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math

from sqlalchemy import bindparam, select, update

from app.core.database import AsyncSessionLocal
from app.models.pitch_appearance import PitchAppearance
from app.services.alignment.landing import hc_to_norm
from app.services.ingest.ingest_services import ZONE_CENTERS
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("backfill_zones")

CHUNK = 50_000


def zone_of(nx: float, ny: float) -> int:
    best_zone, best_dist = 1, float("inf")
    for zone, (cx, cy) in ZONE_CENTERS.items():
        d = math.hypot(nx - cx, ny - cy)
        if d < best_dist:
            best_zone, best_dist = zone, d
    return best_zone


async def main() -> None:
    changed = total = 0
    last_id = None
    async with AsyncSessionLocal() as session:
        while True:
            stmt = (
                select(
                    PitchAppearance.id,
                    PitchAppearance.hc_x,
                    PitchAppearance.hc_y,
                    PitchAppearance.season,
                    PitchAppearance.fielding_zone,
                )
                .where(PitchAppearance.hc_x.is_not(None), PitchAppearance.hc_y.is_not(None))
                .order_by(PitchAppearance.id)
                .limit(CHUNK)
            )
            if last_id is not None:
                stmt = stmt.where(PitchAppearance.id > last_id)
            rows = (await session.execute(stmt)).all()
            if not rows:
                break
            updates = []
            for pid, hc_x, hc_y, season, old_zone in rows:
                nx, ny = hc_to_norm(hc_x, hc_y, season)
                new_zone = zone_of(float(nx), float(ny))
                if new_zone != old_zone:
                    updates.append({"b_pid": pid, "b_zone": new_zone})
            if updates:
                # Core-level update: avoids ORM bulk-update-by-pk semantics
                tbl = PitchAppearance.__table__
                await session.execute(
                    tbl.update()
                    .where(tbl.c.id == bindparam("b_pid"))
                    .values(fielding_zone=bindparam("b_zone")),
                    updates,
                )
                await session.commit()
            changed += len(updates)
            total += len(rows)
            last_id = rows[-1][0]
            logger.info("processed %d (changed %d, %.1f%%)", total, changed, 100 * changed / total)
    logger.info("DONE: %d/%d zones changed (%.2f%%)", changed, total, 100 * changed / max(total, 1))


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    asyncio.run(main())
