"""
PitcherAggregateService — aggregate PitchAppearance rows into one
PitcherProfile per (pitcher, season): batted-ball tendencies, K/BB rates,
velocity, spin, and pitch mix.

The alignment engine reads ``groundball_pct`` to tilt ground-vs-air fielder
positioning (a sinkerballer induces grounders → infield coverage matters more).
Derived entirely from already-ingested pitch data, so it rides the same nightly
job and historical backfill as spray aggregation. xFIP/SIERA are left null
(they require a FanGraphs pull and aren't used by the engine).
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pitch_appearance import PitchAppearance
from app.models.pitcher_profile import PitcherProfile

logger = logging.getLogger(__name__)

FASTBALLS = ("FF", "SI", "FC")
MIN_BATTED_BALLS = 20            # need enough balls in play to trust GB/FB rates
STARTER_PITCHES_PER_GAME = 40    # role heuristic: SP vs RP


def classify_pitcher(gb_pct: float, fb_pct: float, k_pct: float | None) -> str:
    """Map batted-ball / strikeout rates to the paper's pitcher type."""
    if gb_pct >= 0.50:
        return "groundball"
    if fb_pct >= 0.38:
        return "flyball"
    if k_pct is not None and k_pct >= 0.27:
        return "strikeout"
    return "neutral"


def _round(v: float | None, ndigits: int = 1) -> float | None:
    return round(v, ndigits) if v is not None else None


class PitcherAggregateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def aggregate(self, season: int) -> int:
        """Rebuild all PitcherProfile rows for the season. Returns rows written."""
        logger.info("Starting pitcher aggregation for season %d", season)
        await self.session.execute(
            delete(PitcherProfile).where(PitcherProfile.season == season)
        )

        counts = await self._pitcher_counts(season)
        pitch_mix = await self._pitch_mix(season)
        logger.info("Found %d pitchers in %d", len(counts), season)

        written = 0
        for r in counts:
            batted = r["batted"]
            pid = r["pitcher_id"]
            if pid is None or batted < MIN_BATTED_BALLS:
                continue

            gb = r["gb"] / batted
            fb = r["fb"] / batted
            ld = r["ld"] / batted
            pu = r["pu"] / batted
            pa = r["pa"] or 0
            k_pct = (r["k"] / pa) if pa else None
            bb_pct = (r["bb"] / pa) if pa else None
            games = r["games"] or 1
            pitches_per_game = r["pitches"] / games

            self.session.add(PitcherProfile(
                player_id=pid,
                season=season,
                role="SP" if pitches_per_game >= STARTER_PITCHES_PER_GAME else "RP",
                pitcher_type=classify_pitcher(gb, fb, k_pct),
                groundball_pct=round(gb, 4),
                flyball_pct=round(fb, 4),
                linedrive_pct=round(ld, 4),
                popup_pct=round(pu, 4),
                strikeout_pct=round(k_pct, 4) if k_pct is not None else None,
                walk_pct=round(bb_pct, 4) if bb_pct is not None else None,
                avg_velocity_mph=_round(r["avg_velo"]),
                avg_fastball_mph=_round(r["avg_fb_velo"]),
                max_fastball_mph=_round(r["max_fb_velo"]),
                spin_rate_avg=int(r["avg_spin"]) if r["avg_spin"] is not None else None,
                pitch_mix=pitch_mix.get(pid),
            ))
            written += 1

        await self.session.flush()
        logger.info("Pitcher aggregation complete: %d profiles for season %d", written, season)
        return written

    async def _pitcher_counts(self, season: int) -> list[dict]:
        traj = PitchAppearance.ball_trajectory
        speed = PitchAppearance.release_speed_mph
        is_fastball = PitchAppearance.pitch_type.in_(FASTBALLS)
        stmt = (
            select(
                PitchAppearance.pitcher_id,
                func.count().label("pitches"),
                func.count().filter(traj.is_not(None)).label("batted"),
                func.count().filter(traj == "groundball").label("gb"),
                func.count().filter(traj == "flyball").label("fb"),
                func.count().filter(traj == "linedrive").label("ld"),
                func.count().filter(traj == "popup").label("pu"),
                func.count().filter(PitchAppearance.events.is_not(None)).label("pa"),
                func.count().filter(PitchAppearance.events == "strikeout").label("k"),
                func.count().filter(
                    PitchAppearance.events.in_(("walk", "intent_walk"))
                ).label("bb"),
                func.avg(speed).label("avg_velo"),
                func.avg(speed).filter(is_fastball).label("avg_fb_velo"),
                func.max(speed).filter(is_fastball).label("max_fb_velo"),
                func.avg(PitchAppearance.spin_rate).label("avg_spin"),
                func.count(func.distinct(PitchAppearance.game_id)).label("games"),
            )
            .where(
                PitchAppearance.season == season,
                PitchAppearance.pitcher_id.is_not(None),
            )
            .group_by(PitchAppearance.pitcher_id)
        )
        result = await self.session.execute(stmt)
        return [dict(m) for m in result.mappings()]

    async def _pitch_mix(self, season: int) -> dict[object, dict[str, float]]:
        """Per-pitcher pitch-type usage shares, most-used first."""
        stmt = (
            select(
                PitchAppearance.pitcher_id,
                PitchAppearance.pitch_type,
                func.count().label("n"),
            )
            .where(
                PitchAppearance.season == season,
                PitchAppearance.pitcher_id.is_not(None),
                PitchAppearance.pitch_type.is_not(None),
            )
            .group_by(PitchAppearance.pitcher_id, PitchAppearance.pitch_type)
        )
        result = await self.session.execute(stmt)

        by_pitcher: dict[object, dict[str, int]] = {}
        totals: dict[object, int] = {}
        for row in result.mappings():
            pid = row["pitcher_id"]
            by_pitcher.setdefault(pid, {})[row["pitch_type"]] = row["n"]
            totals[pid] = totals.get(pid, 0) + row["n"]

        mix: dict[object, dict[str, float]] = {}
        for pid, counts in by_pitcher.items():
            t = totals[pid] or 1
            mix[pid] = {
                pt: round(n / t, 3)
                for pt, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
            }
        return mix
