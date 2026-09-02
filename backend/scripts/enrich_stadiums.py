"""
Enrich existing stadium rows with curated park geometry — five-point wall
dimensions, wall heights, features — and apply venue migrations (e.g. the
Athletics' move to Sutter Health Park). Idempotent; safe to re-run.

Usage:
    cd backend
    python -m scripts.enrich_stadiums
"""
import asyncio
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
import app.models  # noqa: F401 — register all mappers
from app.models.stadium import Stadium
from app.services.park_data import PARKS_BY_VENUE_ID, VENUE_MIGRATIONS

logging.basicConfig(level=logging.WARNING)


async def enrich() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Stadium))
        stadiums = {s.mlb_venue_id: s for s in result.scalars().all()}

        # Venue moves: re-point the old row at the new venue id so FKs survive
        for old_id, new_id in VENUE_MIGRATIONS.items():
            if old_id in stadiums and new_id not in stadiums:
                stadium = stadiums.pop(old_id)
                stadium.mlb_venue_id = new_id
                stadiums[new_id] = stadium
                print(f"Migrated venue {old_id} -> {new_id}")

        updated = 0
        for venue_id, info in PARKS_BY_VENUE_ID.items():
            stadium = stadiums.get(venue_id)
            if stadium is None:
                print(f"  WARNING: no stadium row for venue {venue_id} ({info.get('name')})")
                continue

            lf, lc, cf, rc, rf = info["dimensions"]
            stadium.name = info.get("name", stadium.name)
            stadium.left_line_ft = lf
            stadium.left_center_ft = lc
            stadium.center_ft = cf
            stadium.right_center_ft = rc
            stadium.right_line_ft = rf
            stadium.roof_type = info.get("roof", stadium.roof_type)
            stadium.surface = info.get("surface", stadium.surface)
            stadium.wall_heights = info.get("wall_heights")
            stadium.features = info.get("features", [])

            heights = info.get("wall_heights") or {}
            stadium.left_wall_ht = heights.get("left_field")
            stadium.right_wall_ht = heights.get("right_field")

            if "city" in info:
                stadium.city = info["city"]
                stadium.state = info.get("state")
                stadium.latitude = info.get("lat")
                stadium.longitude = info.get("lon")
                stadium.altitude_ft = info.get("alt", stadium.altitude_ft)

            updated += 1

        # Team facts that changed alongside venue moves
        from app.models.team import Team
        result = await session.execute(select(Team).where(Team.mlb_team_id == "133"))
        athletics = result.scalar_one_or_none()
        if athletics and athletics.abbreviation != "ATH":
            athletics.name = "Athletics"
            athletics.abbreviation = "ATH"
            print("Updated Athletics name/abbreviation")

        await session.commit()
        print(f"Enriched {updated} stadiums with park geometry.")


if __name__ == "__main__":
    asyncio.run(enrich())
