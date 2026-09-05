"""
Ingest services — pull external data via pybaseball / MLB Stats API and
upsert into Postgres.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_str(value) -> str | None:
    """Return a clean string or None — never the string 'nan'."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value):
        return None
    s = str(value).strip()
    return s if s and s.lower() != "nan" else None


def _safe_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _safe_int(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _pct_from_str(value) -> float | None:
    """Savant formats rates as integer-percent strings ('85%', '-3%') → fraction."""
    if value is None or pd.isna(value):
        return None
    try:
        return float(str(value).strip().rstrip("%")) / 100.0
    except ValueError:
        return None


def _base_occupied(value) -> bool:
    """Statcast on_1b/on_2b/on_3b hold a runner's MLBAM id or NaN."""
    return value is not None and not pd.isna(value)


# ── Player ingest (MLB Stats API rosters) ────────────────────────────────────

class PlayerIngestService:
    """Populate the player table from MLB Stats API team rosters."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(self, season: int) -> int:
        from app.repositories.repositories import PlayerRepository, TeamRepository

        player_repo = PlayerRepository(self.session)
        team_repo = TeamRepository(self.session)
        teams = await team_repo.list(limit=50)
        if not teams:
            logger.warning("No teams seeded — run scripts.seed first")
            return 0

        count = 0
        async with httpx.AsyncClient(base_url=settings.mlb_stats_api_base, timeout=30) as client:
            for team in teams:
                try:
                    resp = await client.get(
                        f"/teams/{team.mlb_team_id}/roster",
                        params={
                            "rosterType": "fullSeason",
                            "season": season,
                            "hydrate": "person",
                        },
                    )
                    resp.raise_for_status()
                    roster = resp.json().get("roster", [])
                except httpx.HTTPError as exc:
                    logger.warning("Roster fetch failed for %s: %s", team.abbreviation, exc)
                    continue

                for entry in roster:
                    person = entry.get("person", {})
                    mlbam_id = person.get("id")
                    if not mlbam_id:
                        continue

                    birth_date = person.get("birthDate")
                    debut = person.get("mlbDebutDate")
                    defaults = {
                        "full_name": person.get("fullName", ""),
                        "first_name": person.get("firstName", person.get("useName", "")),
                        "last_name": person.get("lastName", ""),
                        "position": person.get("primaryPosition", {}).get("abbreviation", "UT")[:5],
                        "throws": person.get("pitchHand", {}).get("code", "R")[:1],
                        "bats": person.get("batSide", {}).get("code", "R")[:1],
                        "birth_date": datetime.strptime(birth_date, "%Y-%m-%d").date() if birth_date else None,
                        "birth_country": person.get("birthCountry"),
                        "active": person.get("active", True),
                        "pro_debut": datetime.strptime(debut, "%Y-%m-%d").date() if debut else None,
                        "team_id": team.id,
                    }
                    await player_repo.upsert(
                        lookup={"mlbam_id": str(mlbam_id)},
                        defaults=defaults,
                    )
                    count += 1

                logger.info("Roster loaded: %s (%d players so far)", team.abbreviation, count)

        await self.session.flush()
        logger.info("Player ingest complete: %d players", count)
        return count


# ── Statcast ingest ───────────────────────────────────────────────────────────

PITCH_TYPE_LABELS: dict[str, str] = {
    "FF": "Four-Seam Fastball", "SI": "Sinker", "FC": "Cutter",
    "SL": "Slider", "ST": "Sweeper", "CU": "Curveball", "KC": "Knuckle Curve",
    "CH": "Changeup", "FS": "Splitter", "KN": "Knuckleball",
    "EP": "Eephus", "FO": "Forkball", "SC": "Screwball", "SV": "Slurve",
}

SPEED_LEVELS: list[tuple[float, float, int]] = [
    (0, 77.9, 1), (78, 81.9, 2), (82, 86.9, 3),
    (87, 91.9, 4), (92, 95.9, 5), (96, 99.9, 6), (100, 999, 7),
]

ZONE_CENTERS = {
    1: (0.65, 0.30), 2: (0.55, 0.35), 3: (0.45, 0.35), 4: (0.35, 0.30),
    5: (0.20, 0.70), 6: (0.35, 0.80), 7: (0.65, 0.80), 8: (0.80, 0.70),
}


def _speed_level(mph: float | None) -> int | None:
    if mph is None or pd.isna(mph):
        return None
    for lo, hi, level in SPEED_LEVELS:
        if lo <= mph <= hi:
            return level
    return None


def _fielding_zone_from_hc(hc_x: float | None, hc_y: float | None, season: int) -> int | None:
    """Map Statcast hc_x / hc_y to fielding zone 1–8 via the canonical
    era-aware transform (services/alignment/landing.hc_to_norm — calibrated
    against measured hit distances, EXPERIMENTS.md 2026-09-04)."""
    if hc_x is None or hc_y is None or pd.isna(hc_x) or pd.isna(hc_y):
        return None
    from app.services.alignment.landing import hc_to_norm

    nx_a, ny_a = hc_to_norm(float(hc_x), float(hc_y), season)
    nx, ny = float(nx_a), float(ny_a)

    import math
    best_zone, best_dist = 1, float("inf")
    for zone, (cx, cy) in ZONE_CENTERS.items():
        d = math.sqrt((nx - cx) ** 2 + (ny - cy) ** 2)
        if d < best_dist:
            best_zone, best_dist = zone, d
    return best_zone


def _general_result(events: str | None) -> str | None:
    if not events or pd.isna(events):
        return None
    hits = {"single", "double", "triple", "home_run"}
    outs = {
        "field_out", "strikeout", "grounded_into_double_play",
        "force_out", "double_play", "fielders_choice_out",
        "strikeout_double_play", "other_out",
    }
    if events in hits:
        return "hit"
    if events in outs or "out" in events:
        return "out"
    return None


def _specific_result(events: str | None) -> str | None:
    if not events or pd.isna(events):
        return None
    mapping = {
        "single": "single", "double": "double",
        "triple": "triple", "home_run": "hr",
        "field_error": "error",
    }
    if events in mapping:
        return mapping[events]
    if _general_result(events) == "out":
        return "out"
    return None


def _ball_trajectory(bb_type: str | None) -> str | None:
    if not bb_type or pd.isna(bb_type):
        return None
    mapping = {
        "ground_ball": "groundball", "fly_ball": "flyball",
        "line_drive": "linedrive", "popup": "popup",
    }
    return mapping.get(bb_type)


class StatcastIngestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(self, start_date: str, end_date: str) -> int:
        """Pull Statcast data for date range and upsert into pitch_appearance."""
        import asyncio
        import pybaseball

        logger.info("Fetching Statcast data %s → %s", start_date, end_date)

        # pybaseball is synchronous — run in thread pool
        loop = asyncio.get_event_loop()
        df: pd.DataFrame = await loop.run_in_executor(
            None, lambda: pybaseball.statcast(start_dt=start_date, end_dt=end_date)
        )

        if df is None or df.empty:
            logger.warning("No Statcast data returned for %s → %s", start_date, end_date)
            return 0

        # Statcast occasionally returns the same pitch twice — drop exact
        # play-key duplicates so the unique mlb_play_id constraint holds.
        before = len(df)
        df = df.drop_duplicates(subset=["game_pk", "at_bat_number", "pitch_number"], keep="last")
        if len(df) < before:
            logger.warning("Dropped %d duplicate Statcast rows", before - len(df))

        logger.info("Statcast returned %d rows", len(df))
        count = 0
        from sqlalchemy import delete
        from app.repositories.repositories import PlayerRepository
        from app.models.pitch_appearance import PitchAppearance

        # Idempotent re-runs: clear existing rows in this date window
        await self.session.execute(
            delete(PitchAppearance).where(
                PitchAppearance.game_date >= datetime.strptime(start_date, "%Y-%m-%d").date(),
                PitchAppearance.game_date <= datetime.strptime(end_date, "%Y-%m-%d").date(),
            )
        )

        player_repo = PlayerRepository(self.session)

        # Cache MLBAM id → player UUID to avoid one query per row
        player_cache: dict[str, object] = {}

        async def resolve_player(mlbam) -> object | None:
            if mlbam is None or pd.isna(mlbam):
                return None
            key = str(int(mlbam))
            if key not in player_cache:
                p = await player_repo.get_by_mlbam_id(key)
                player_cache[key] = p.id if p else None
            return player_cache[key]

        for _, row in df.iterrows():
            try:
                pitcher_id = await resolve_player(row.get("pitcher"))
                batter_id = await resolve_player(row.get("batter"))

                game_date = row.get("game_date")
                if game_date is not None and not pd.isna(game_date):
                    game_date = pd.to_datetime(game_date).date()
                else:
                    game_date = None

                pitch_type = _safe_str(row.get("pitch_type"))

                obj = PitchAppearance(
                    mlb_play_id=f"{row.get('game_pk', '')}-{row.get('at_bat_number', '')}-{row.get('pitch_number', '')}",
                    game_id=str(row.get("game_pk", "")),
                    game_date=game_date,
                    season=_safe_int(row.get("game_year")) or int(str(start_date)[:4]),
                    inning=_safe_int(row.get("inning")) or 1,
                    inning_half=str(row.get("inning_topbot", "top")).lower(),
                    pitcher_id=pitcher_id,
                    batter_id=batter_id,
                    pitch_type=pitch_type,
                    pitch_type_label=PITCH_TYPE_LABELS.get(pitch_type or "", None),
                    release_speed_mph=_safe_float(row.get("release_speed")),
                    release_speed_level=_speed_level(row.get("release_speed")),
                    spin_rate=_safe_int(row.get("release_spin_rate")),
                    pfx_x=_safe_float(row.get("pfx_x")),
                    pfx_z=_safe_float(row.get("pfx_z")),
                    plate_x=_safe_float(row.get("plate_x")),
                    plate_z=_safe_float(row.get("plate_z")),
                    zone=_safe_int(row.get("zone")),
                    balls=_safe_int(row.get("balls")) or 0,
                    strikes=_safe_int(row.get("strikes")) or 0,
                    outs_when_up=_safe_int(row.get("outs_when_up")) or 0,
                    on_1b=_base_occupied(row.get("on_1b")),
                    on_2b=_base_occupied(row.get("on_2b")),
                    on_3b=_base_occupied(row.get("on_3b")),
                    events=_safe_str(row.get("events")),
                    description=_safe_str(row.get("description")),
                    bb_type=_safe_str(row.get("bb_type")),
                    launch_angle=_safe_float(row.get("launch_angle")),
                    launch_speed=_safe_float(row.get("launch_speed")),
                    hit_distance_sc=_safe_float(row.get("hit_distance_sc")),
                    hc_x=_safe_float(row.get("hc_x")),
                    hc_y=_safe_float(row.get("hc_y")),
                    fielding_zone=_fielding_zone_from_hc(
                        row.get("hc_x"), row.get("hc_y"),
                        _safe_int(row.get("game_year")) or int(str(start_date)[:4]),
                    ),
                    general_result=_general_result(_safe_str(row.get("events"))),
                    specific_result=_specific_result(_safe_str(row.get("events"))),
                    ball_trajectory=_ball_trajectory(_safe_str(row.get("bb_type"))),
                    if_fielding_alignment=_safe_str(row.get("if_fielding_alignment")),
                    of_fielding_alignment=_safe_str(row.get("of_fielding_alignment")),
                )
                self.session.add(obj)
                count += 1
                if count % 500 == 0:
                    await self.session.flush()
                    logger.debug("Flushed %d pitch appearances", count)
            except Exception as exc:
                logger.warning("Skipping row: %s", exc)

        await self.session.flush()
        logger.info("Statcast ingest complete: %d records", count)
        return count


# ── Fielding / OAA ingest ─────────────────────────────────────────────────────

class FieldingIngestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(self, season: int) -> int:
        import asyncio
        import pybaseball

        logger.info("Fetching fielding OAA data for season %d", season)

        loop = asyncio.get_event_loop()
        oaa_df: pd.DataFrame = await loop.run_in_executor(
            None, lambda: pybaseball.statcast_outs_above_average(season, pos="all")
        )

        if oaa_df is None or oaa_df.empty:
            logger.warning("No OAA data for season %d", season)
            return 0

        sprint_df: pd.DataFrame = await loop.run_in_executor(
            None, lambda: pybaseball.statcast_sprint_speed(season)
        )

        from app.repositories.repositories import FieldingRepository, PlayerRepository
        from app.models.fielding_profile import FieldingProfile
        from app.services.injury_service import _sprint_level, _range_level

        player_repo = PlayerRepository(self.session)
        fielding_repo = FieldingRepository(self.session)
        count = 0

        for _, row in oaa_df.iterrows():
            try:
                mlbam_id = str(int(row["player_id"]))
                player = await player_repo.get_by_mlbam_id(mlbam_id)
                if player is None:
                    continue

                position = str(row.get("primary_pos_formatted", "OF")).strip()

                # Merge sprint speed (ft/s — NOT hp_to_1b, which is seconds)
                sprint_speed = None
                if sprint_df is not None and not sprint_df.empty and "sprint_speed" in sprint_df.columns:
                    match = sprint_df[sprint_df["player_id"] == int(mlbam_id)]
                    if not match.empty:
                        sprint_speed = _safe_float(match.iloc[0]["sprint_speed"])

                defaults = {
                    # NOTE: the OAA leaderboard has NO games/innings/attempts
                    # columns — these stay 0 (DATA_KNOWLEDGE.md 2026-09-04);
                    # the playing-time-honest signal is the success rates below
                    "games": _safe_int(row.get("n_games")) or 0,
                    "innings": _safe_float(row.get("innings")) or 0.0,
                    "actual_success_rate": _pct_from_str(row.get("actual_success_rate_formatted")),
                    "estimated_success_rate": _pct_from_str(row.get("adj_estimated_success_rate_formatted")),
                    "diff_success_rate": _pct_from_str(row.get("diff_success_rate_formatted")),
                    "sprint_speed_ft_s": sprint_speed,
                    "sprint_speed_level": _sprint_level(sprint_speed),
                    "outs_above_average": _safe_float(row.get("outs_above_average")),
                    "oaa_back": _safe_float(row.get("outs_above_average_behind")) if "outs_above_average_behind" in row.index else None,
                    "oaa_in": _safe_float(row.get("outs_above_average_toward")) if "outs_above_average_toward" in row.index else None,
                    "fielding_run_value": _safe_float(row.get("fielding_runs_prevented")) if "fielding_runs_prevented" in row.index else None,
                }

                await fielding_repo.upsert(
                    lookup={"player_id": player.id, "season": season, "position": position},
                    defaults=defaults,
                )
                count += 1
            except Exception as exc:
                logger.warning("Skipping fielding row: %s", exc)

        await self.session.flush()
        logger.info("Fielding ingest complete: %d records", count)
        return count
