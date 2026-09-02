"""
SprayAggregateService — nightly job that aggregates PitchAppearance rows
into BatterSprayProfile zone-level summaries.

For each (batter, season, pitch_type, pitcher_hand) combination, counts
hits/outs/trajectories per fielding zone (1–8) and writes one row per zone.
A null pitch_type/pitcher_hand row represents the "all" aggregate.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pitch_appearance import PitchAppearance
from app.models.player import Player
from app.models.remaining_models import BatterSprayProfile

logger = logging.getLogger(__name__)

TRAJECTORIES = ("groundball", "flyball", "linedrive", "popup")
SPECIFIC_RESULTS = ("single", "double", "triple", "hr", "error")
COUNT_FIELDS = ("total", "hits", "outs") + TRAJECTORIES + SPECIFIC_RESULTS

# A scenario combo (pitch type or pitcher hand) needs this many batted balls
# to get its own rows
MIN_COMBO_SAMPLE = 10

# Pitch speed bands: (label_min, label_max) — stored on pitch_speed_min/max
SPEED_BANDS: tuple[tuple[float, float], ...] = ((0.0, 90.0), (90.0, 110.0))

FLUSH_EVERY = 500


class SprayAggregateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def aggregate(self, season: int) -> int:
        """
        Rebuild all BatterSprayProfile rows for the given season.
        Returns total rows written.
        """
        logger.info("Starting spray aggregation for season %d", season)

        await self.session.execute(
            delete(BatterSprayProfile).where(BatterSprayProfile.season == season)
        )

        # batter_id -> (pitch_type, pitcher_hand) -> zone -> counts
        by_batter = await self._zone_counts(season)
        logger.info("Found %d batters with batted balls in %d", len(by_batter), season)

        rows_written = 0
        unflushed = 0

        for batter_id, by_combo in by_batter.items():
            # "all pitches, all hands, all speeds" aggregate
            all_zones = self._sum_zones(by_combo.values())
            written = self._write_profiles(batter_id, season, None, None, None, all_zones)

            by_pitch: dict[str, list] = {}
            by_hand: dict[str, list] = {}
            by_band: dict[int, list] = {}
            for (pitch_type, hand, band), zones in by_combo.items():
                if pitch_type is not None:
                    by_pitch.setdefault(pitch_type, []).append(zones)
                if hand in ("L", "R"):
                    by_hand.setdefault(hand, []).append(zones)
                if band is not None:
                    by_band.setdefault(band, []).append(zones)

            # per pitch type (across hands/speeds)
            for pitch_type, zone_groups in by_pitch.items():
                zones = self._sum_zones(zone_groups)
                if sum(c["total"] for c in zones.values()) < MIN_COMBO_SAMPLE:
                    continue
                written += self._write_profiles(batter_id, season, pitch_type, None, None, zones)

            # per pitcher hand (across pitch types/speeds)
            for hand, zone_groups in by_hand.items():
                zones = self._sum_zones(zone_groups)
                if sum(c["total"] for c in zones.values()) < MIN_COMBO_SAMPLE:
                    continue
                written += self._write_profiles(batter_id, season, None, hand, None, zones)

            # per speed band (across pitch types/hands)
            for band, zone_groups in by_band.items():
                zones = self._sum_zones(zone_groups)
                if sum(c["total"] for c in zones.values()) < MIN_COMBO_SAMPLE:
                    continue
                written += self._write_profiles(
                    batter_id, season, None, None, SPEED_BANDS[band], zones
                )

            rows_written += written
            unflushed += written
            if unflushed >= FLUSH_EVERY:
                await self.session.flush()
                unflushed = 0

        await self.session.flush()
        logger.info("Spray aggregation complete: %d rows for season %d", rows_written, season)
        return rows_written

    async def _zone_counts(
        self, season: int
    ) -> dict[object, dict[tuple[str | None, str | None], dict[int, dict[str, int]]]]:
        """
        One pass over the season: per (batter, pitch_type, pitcher_hand,
        fielding_zone), count total batted balls plus each outcome/trajectory
        via FILTER. Pitcher hand comes from the pitcher's player row.
        """
        speed_band = case(
            (PitchAppearance.release_speed_mph.is_(None), None),
            (PitchAppearance.release_speed_mph < SPEED_BANDS[1][0], 0),
            else_=1,
        ).label("speed_band")

        stmt = (
            select(
                PitchAppearance.batter_id,
                PitchAppearance.pitch_type,
                Player.throws.label("pitcher_hand"),
                speed_band,
                PitchAppearance.fielding_zone,
                func.count().label("total"),
                func.count()
                .filter(PitchAppearance.general_result == "hit")
                .label("hits"),
                func.count()
                .filter(PitchAppearance.general_result == "out")
                .label("outs"),
                *(
                    func.count()
                    .filter(PitchAppearance.ball_trajectory == t)
                    .label(t)
                    for t in TRAJECTORIES
                ),
                *(
                    func.count()
                    .filter(PitchAppearance.specific_result == s)
                    .label(s)
                    for s in SPECIFIC_RESULTS
                ),
            )
            .join(Player, Player.id == PitchAppearance.pitcher_id, isouter=True)
            .where(
                PitchAppearance.season == season,
                PitchAppearance.batter_id.is_not(None),
                PitchAppearance.fielding_zone.is_not(None),
            )
            .group_by(
                PitchAppearance.batter_id,
                PitchAppearance.pitch_type,
                Player.throws,
                speed_band,
                PitchAppearance.fielding_zone,
            )
        )
        result = await self.session.execute(stmt)

        by_batter: dict = {}
        for row in result.mappings():
            counts = {field: row[field] for field in COUNT_FIELDS}
            combo = (row["pitch_type"], row["pitcher_hand"], row["speed_band"])
            by_batter.setdefault(row["batter_id"], {}).setdefault(combo, {})[
                row["fielding_zone"]
            ] = counts
        return by_batter

    @staticmethod
    def _sum_zones(per_combo_zones) -> dict[int, dict[str, int]]:
        """Sum per-combo zone counts into an aggregate."""
        summed: dict[int, dict[str, int]] = {}
        for zones in per_combo_zones:
            for zone, counts in zones.items():
                acc = summed.setdefault(zone, dict.fromkeys(COUNT_FIELDS, 0))
                for field in COUNT_FIELDS:
                    acc[field] += counts[field]
        return summed

    def _write_profiles(
        self,
        batter_id,
        season: int,
        pitch_type: str | None,
        pitcher_hand: str | None,
        speed_band: tuple[float, float] | None,
        zones: dict[int, dict[str, int]],
    ) -> int:
        """Add one BatterSprayProfile per zone with data for this combo."""
        now = datetime.now(timezone.utc)
        rows_written = 0

        for zone, c in sorted(zones.items()):
            total = c["total"]
            if total == 0:
                continue

            profile = BatterSprayProfile(
                player_id=batter_id,
                season=season,
                pitch_type=pitch_type,
                pitcher_hand=pitcher_hand,
                pitch_speed_min=speed_band[0] if speed_band else None,
                pitch_speed_max=speed_band[1] if speed_band else None,
                fielding_zone=zone,
                hit_count=c["hits"],
                out_count=c["outs"],
                total_batted_balls=total,
                hit_pct=c["hits"] / total,
                out_pct=c["outs"] / total,
                groundball_pct=c["groundball"] / total,
                flyball_pct=c["flyball"] / total,
                linedrive_pct=c["linedrive"] / total,
                popup_pct=c["popup"] / total,
                single_pct=c["single"] / total,
                double_pct=c["double"] / total,
                triple_pct=c["triple"] / total,
                hr_pct=c["hr"] / total,
                error_pct=c["error"] / total,
                sample_n=total,
                last_updated=now,
            )
            self.session.add(profile)
            rows_written += 1

        return rows_written
