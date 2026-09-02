"""
AlignmentService orchestrates the full recommendation flow:
  1. Cache check (Redis)
  2. Parallel data fetch (spray, fielding profiles, weather)
  3. Injury factor application
  4. AlignmentEngine.compute_alignment()
  5. Persist + cache result
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.redis import cache_get, cache_set
from app.models.remaining_models import DefensiveAlignment
from app.repositories.repositories import (
    AlignmentRepository,
    FieldingRepository,
    PitcherRepository,
    SprayRepository,
    StadiumRepository,
    WeatherRepository,
)
from app.schemas.schemas import (
    AlignmentRequest,
    AlignmentResponse,
    AlignmentScoreRequest,
    AlignmentScoreResponse,
    AlignmentSummary,
    FielderPosition,
)
from app.services.alignment.engine import (
    GRID,
    STANDARD_POSITIONS,
    AlignmentCandidate,
    build_hit_probability_grid,
    carry_factor,
    compute_alignment,
    is_legal_position,
    resolve_batter_hand,
    score_custom_positions,
)
from app.services.injury_service import InjuryService
from app.services.spray_blend import merge_zone_rows
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)
settings = get_settings()


def _request_cache_key(req: AlignmentRequest) -> str:
    payload = json.dumps(
        {
            "batter": str(req.batter_id),
            "pitcher": str(req.pitcher_id),
            "stadium": str(req.stadium_id),
            "weather": str(req.weather_id),
            "weather_manual": req.weather.model_dump() if req.weather is not None else None,
            "inning": req.inning,
            "outs": req.outs,
            "runners": req.runners,
            "optimize_for": req.optimize_for,
            "factors": sorted(req.include_factors),
            "roster": sorted(f"{e.position}:{e.player_id}" for e in req.active_roster),
        },
        sort_keys=True,
    )
    return f"alignment:{hashlib.sha1(payload.encode()).hexdigest()}"


class AlignmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.spray_repo = SprayRepository(session)
        self.fielding_repo = FieldingRepository(session)
        self.pitcher_repo = PitcherRepository(session)
        self.weather_repo = WeatherRepository(session)
        self.stadium_repo = StadiumRepository(session)
        self.alignment_repo = AlignmentRepository(session)
        self.injury_svc = InjuryService(session)

    async def _park_context(
        self, stadium_id: uuid.UUID | None
    ) -> tuple[dict[str, int] | None, float]:
        """(park dimensions, altitude_ft) for the stadium — one fetch feeds both
        the fence bounds and the weather carry model."""
        if stadium_id is None:
            return None, 0.0
        stadium = await self.stadium_repo.get(stadium_id)
        if stadium is None:
            return None, 0.0
        from app.services.park_layout import stadium_dimensions
        return stadium_dimensions(stadium), float(stadium.altitude_ft or 0.0)

    async def _resolve_weather(self, req) -> Any:
        """Inline manual weather wins over a saved weather_id; either may be None."""
        if getattr(req, "weather", None) is not None:
            from app.services.weather_service import build_manual_weather
            return build_manual_weather(req.stadium_id, req.weather)
        if getattr(req, "weather_id", None) is not None:
            return await self.weather_repo.get(req.weather_id)
        return None

    async def _spray_zones(self, batter_id: uuid.UUID, season: int | None):
        """Spray zones for the alignment engine.

        ``season=None`` or ``0`` returns a recency-weighted blend across every
        season the batter has data for (same logic as the spray-chart "Total"),
        so recommendations track recent tendencies and the 2023 shift-rule era.
        A specific season returns just that season's rows.
        """
        if season in (None, 0):
            rows = await self.spray_repo.get_zones(batter_id, None)
            return merge_zone_rows(rows, settings.spray_recency_decay)
        return await self.spray_repo.get_zones(batter_id, season)

    async def _batter_hand(
        self, batter_id: uuid.UUID | None, pitcher_id: uuid.UUID | None
    ) -> str | None:
        """Effective batting hand ('L'/'R') for shift aiming, resolving switch
        hitters against the pitcher's throwing hand. None when the batter is
        unknown (engine falls back to canonical geometry)."""
        if batter_id is None:
            return None
        from sqlalchemy import select
        from app.models.player import Player
        ids = [i for i in (batter_id, pitcher_id) if i is not None]
        rows = {
            r[0]: (r[1], r[2])
            for r in (
                await self.session.execute(
                    select(Player.id, Player.bats, Player.throws).where(Player.id.in_(ids))
                )
            ).all()
        }
        bats = rows.get(batter_id, (None, None))[0]
        pitcher_throws = rows.get(pitcher_id, (None, None))[1]
        return resolve_batter_hand(bats, pitcher_throws)

    async def recommend(self, req: AlignmentRequest) -> AlignmentResponse:
        cache_key = _request_cache_key(req)

        # ── 1. Cache check ────────────────────────────────────────────────────
        cached = await cache_get(cache_key)
        if cached:
            logger.debug("Alignment cache hit: %s", cache_key)
            return AlignmentResponse(**cached)

        # ── 2. Data fetch ─────────────────────────────────────────────────────
        # NOTE: one AsyncSession cannot run queries concurrently — fetch
        # sequentially rather than via asyncio.gather.
        # Recommendations blend all seasons with recency weighting so positioning
        # tracks the batter's recent tendencies rather than a single fixed year.
        spray_zones = await self._spray_zones(req.batter_id, None)
        weather = await self._resolve_weather(req)
        pitcher_profile = (
            await self.pitcher_repo.get_latest_profile(req.pitcher_id)
            if "pitcher_type" in req.include_factors
            else None
        )

        roster = {entry.position: entry.player_id for entry in req.active_roster}
        profile_results = {
            pos: await self.fielding_repo.get_latest_profile(pid)
            for pos, pid in roster.items()
        }

        # ── 3. Apply injury factors ───────────────────────────────────────────
        adjusted_profiles: dict[str, Any] = {}
        for pos, profile in profile_results.items():
            if profile is None:
                continue
            entry = next((e for e in req.active_roster if e.position == pos), None)
            if entry and entry.injury_override:
                # Manual in-game override takes precedence
                from app.services.injury_service import AdjustedProfile
                adj = AdjustedProfile.from_profile(profile)
                for attr, factor in entry.injury_override.items():
                    if hasattr(adj, attr):
                        setattr(adj, attr, getattr(adj, attr, 1.0) * factor)
                adjusted_profiles[pos] = adj
            else:
                adjusted_profiles[pos] = await self.injury_svc.apply_for_player(profile)

        # ── 4. Engine ─────────────────────────────────────────────────────────
        dimensions, altitude = await self._park_context(req.stadium_id)
        bats = await self._batter_hand(req.batter_id, req.pitcher_id)
        candidates = compute_alignment(
            spray_zones=spray_zones,
            fielder_profiles=adjusted_profiles,
            roster=roster,
            weather=weather,
            optimize_for=req.optimize_for,
            top_n=settings.alignment_top_n,
            dimensions=dimensions,
            pitcher_profile=pitcher_profile,
            altitude_ft=altitude,
            bats=bats,
        )

        if not candidates:
            # Fallback to standard alignment
            from app.services.alignment.engine import AlignmentCandidate, STANDARD_POSITIONS
            candidates = [AlignmentCandidate(
                shift_type="standard",
                positions=STANDARD_POSITIONS.copy(),
                oaa_delta=0.0,
                hit_pct=0.5,
                confidence=0.1,
            )]

        best = candidates[0]

        # ── 5. Build response ─────────────────────────────────────────────────
        alignment_id = uuid.uuid4()
        player_names = await self._player_names(list(roster.values()))
        fielder_positions = _build_fielder_positions(best, roster, player_names)
        coverage_map = _build_coverage_map(best, adjusted_profiles, roster)

        # Factors actually used — only report a factor when its data was present
        _missing = {
            "batter_spray": not spray_zones,
            "weather": weather is None,
            "pitcher_type": pitcher_profile is None,
        }
        factors_applied = [f for f in req.include_factors if not _missing.get(f, False)]

        response = AlignmentResponse(
            alignment_id=alignment_id,
            shift_type=best.shift_type,
            fielder_positions=fielder_positions,
            coverage_map=coverage_map,
            overlap_zones=[],
            predicted_oaa_delta=best.oaa_delta,
            predicted_hit_pct=best.hit_pct,
            predicted_out_pct=round(1.0 - best.hit_pct, 4),
            confidence=best.confidence,
            optimize_for=req.optimize_for,
            factors_applied=factors_applied,
            alternatives=[
                AlignmentSummary(
                    shift_type=c.shift_type,
                    predicted_oaa_delta=c.oaa_delta,
                    predicted_hit_pct=c.hit_pct,
                    confidence=c.confidence,
                )
                for c in candidates[1:]
            ],
            created_at=datetime.now(timezone.utc),
            pitcher_type=pitcher_profile.pitcher_type if pitcher_profile else None,
            pitcher_groundball_pct=(
                pitcher_profile.groundball_pct if pitcher_profile else None
            ),
            weather_carry=(
                round(carry_factor(weather, altitude), 4) if weather is not None else None
            ),
        )

        # ── 6. Persist + cache ────────────────────────────────────────────────
        await self._persist(req, best, alignment_id, factors_applied)
        await cache_set(
            cache_key, response.model_dump(), settings.cache_ttl_alignment
        )

        return response

    async def _player_names(self, player_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not player_ids:
            return {}
        from sqlalchemy import select
        from app.models.player import Player
        stmt = select(Player.id, Player.full_name).where(Player.id.in_(player_ids))
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def score_custom(self, req: AlignmentScoreRequest) -> AlignmentScoreResponse:
        """Score a user-arranged alignment without persisting or caching."""
        spray_zones = await self._spray_zones(req.batter_id, req.season)
        weather = await self._resolve_weather(req)

        roster = {entry.position: entry.player_id for entry in req.active_roster}
        adjusted_profiles: dict[str, Any] = {}
        for pos, pid in roster.items():
            profile = await self.fielding_repo.get_latest_profile(pid)
            if profile is not None:
                adjusted_profiles[pos] = await self.injury_svc.apply_for_player(profile)

        positions = {pos: (p.x, p.y) for pos, p in req.positions.items()}
        dimensions, altitude = await self._park_context(req.stadium_id)
        bats = await self._batter_hand(req.batter_id, getattr(req, "pitcher_id", None))
        candidate = score_custom_positions(
            custom_positions=positions,
            spray_zones=spray_zones,
            fielder_profiles=adjusted_profiles,
            roster=roster,
            weather=weather,
            optimize_for=req.optimize_for,
            dimensions=dimensions,
            altitude_ft=altitude,
            bats=bats,
        )

        illegal = [
            pos for pos, (x, y) in positions.items()
            if not is_legal_position(pos, x, y, dimensions)
        ]
        return AlignmentScoreResponse(
            shift_type="custom",
            predicted_oaa_delta=candidate.oaa_delta,
            predicted_hit_pct=candidate.hit_pct,
            predicted_out_pct=round(1.0 - candidate.hit_pct, 4),
            confidence=candidate.confidence,
            legal=candidate.legal,
            illegal_positions=illegal,
        )

    async def _persist(
        self,
        req: AlignmentRequest,
        best: AlignmentCandidate,
        alignment_id: uuid.UUID,
        factors_applied: list[str],
    ) -> None:
        try:
            await self.alignment_repo.create(
                id=alignment_id,
                alignment_type="recommendation",
                team_id=req.team_id,
                batter_id=req.batter_id,
                pitcher_id=req.pitcher_id,
                stadium_id=req.stadium_id,
                weather_id=req.weather_id,
                inning=req.inning,
                outs=req.outs,
                on_1b=req.runners.get("on_1b", False),
                on_2b=req.runners.get("on_2b", False),
                on_3b=req.runners.get("on_3b", False),
                score_diff=req.score_diff,
                shift_type=best.shift_type,
                fielder_positions=best.positions,
                predicted_oaa_delta=best.oaa_delta,
                predicted_hit_pct=best.hit_pct,
                predicted_out_pct=round(1.0 - best.hit_pct, 4),
                confidence=best.confidence,
                factors_used=factors_applied,
                optimize_for=req.optimize_for,
            )
        except Exception as exc:
            logger.warning("Failed to persist alignment: %s", exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

from typing import Any


def _build_fielder_positions(
    candidate: AlignmentCandidate,
    roster: dict[str, uuid.UUID],
    player_names: dict[uuid.UUID, str] | None = None,
) -> dict[str, FielderPosition]:
    names = player_names or {}
    result: dict[str, FielderPosition] = {}
    for pos, (cx, cy) in candidate.positions.items():
        if pos in ("C", "P"):
            continue
        # Convert normalized coords to depth_ft and angle_deg
        # depth_ft: distance from home plate (y=0), ~400ft deep field
        depth_ft = cy * 400.0
        # angle: 0° = center field axis, positive = toward right field
        angle_deg = (cx - 0.5) * 90.0

        pid = roster.get(pos)
        result[pos] = FielderPosition(
            player_id=pid or uuid.uuid4(),
            player_name=names.get(pid, pos) if pid else pos,
            x=cx,
            y=cy,
            depth_ft=round(depth_ft, 1),
            angle_deg=round(angle_deg, 1),
            catch_prob_zone=0.0,  # populated by frontend from coverage_map
        )
    return result


def _build_coverage_map(
    candidate: AlignmentCandidate,
    profiles: dict[str, Any],
    roster: dict[str, uuid.UUID],
) -> list[list[float]]:
    from app.services.alignment.engine import FielderReach, compute_reach
    import numpy as np

    combined = np.zeros((GRID, GRID), dtype=np.float32)
    for pos, (cx, cy) in candidate.positions.items():
        if pos in ("C", "P"):
            continue
        profile = profiles.get(pos)
        reach = compute_reach(
            player_id=roster.get(pos, uuid.uuid4()),
            position=pos,
            center_x=cx,
            center_y=cy,
            sprint_speed=getattr(profile, "sprint_speed_ft_s", None) if profile else None,
            reaction_time=getattr(profile, "reaction_time_s", None) if profile else None,
            route_efficiency=getattr(profile, "route_efficiency_pct", None) if profile else None,
        )
        combined = np.maximum(combined, reach.coverage_grid())

    # Halve transport size: 100×100 → 50×50, rounded
    g = combined.shape[0]
    if g % 2 == 0:
        combined = combined.reshape(g // 2, 2, g // 2, 2).mean(axis=(1, 3))
    return np.round(combined, 4).tolist()
