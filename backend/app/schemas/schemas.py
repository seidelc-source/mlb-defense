"""
All Pydantic v2 request/response schemas.
Organized in one file for the scaffold; split per resource as the project grows.
"""
import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ─── Shared ───────────────────────────────────────────────────────────────────

class PlayerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    position: str
    throws: str
    bats: str
    team_id: uuid.UUID | None = None
    active: bool


class TeamSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    abbreviation: str
    league: str
    division: str
    home_stadium_id: uuid.UUID | None = None


# ─── Players ──────────────────────────────────────────────────────────────────

class PlayerDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    mlbam_id: str | None
    fangraphs_id: str | None
    bbref_id: str | None
    full_name: str
    first_name: str
    last_name: str
    position: str
    throws: str
    bats: str
    birth_date: date | None
    birth_country: str | None
    active: bool
    pro_debut: date | None
    team_id: uuid.UUID | None


class PlayerListResponse(BaseModel):
    total: int
    players: list[PlayerSummary]


# ─── Fielding ─────────────────────────────────────────────────────────────────

class InjuryFactors(BaseModel):
    body_part: str
    severity: str
    speed_factor: float
    arm_strength_factor: float
    arm_accuracy_factor: float
    reaction_factor: float
    range_factor: float


class FieldingProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    player: PlayerSummary
    season: int
    position: str
    games: int
    innings: float

    sprint_speed_ft_s: float | None
    sprint_speed_level: int | None
    range_pct_vs_avg: float | None
    range_level: int | None
    reaction_time_s: float | None
    reaction_time_level: int | None
    route_efficiency_pct: float | None
    route_efficiency_level: int | None
    arm_strength_mph: float | None
    arm_strength_level: int | None
    arm_accuracy_pct: float | None
    arm_accuracy_level: int | None

    outs_above_average: float | None
    oaa_back: float | None
    oaa_in: float | None
    oaa_left: float | None
    oaa_right: float | None
    fielding_run_value: float | None
    fielder_throwing_runs: float | None

    injury_adjusted: bool = False
    injury_factors: list[InjuryFactors] | None = None


class PitcherProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    player: PlayerSummary
    season: int
    role: str               # SP | RP
    pitcher_type: str       # groundball | flyball | strikeout | neutral

    groundball_pct: float | None
    flyball_pct: float | None
    linedrive_pct: float | None
    popup_pct: float | None
    strikeout_pct: float | None
    walk_pct: float | None

    avg_velocity_mph: float | None
    avg_fastball_mph: float | None
    max_fastball_mph: float | None
    spin_rate_avg: int | None
    pitch_mix: dict[str, float] | None


# ─── Spray charts ─────────────────────────────────────────────────────────────

class SprayZone(BaseModel):
    zone: int = Field(..., ge=1, le=8, description="Fielding zone 1–8 per paper's Table 2")
    hit_pct: float
    out_pct: float
    trajectory: dict[str, float]  # groundball / flyball / linedrive / popup
    specific: dict[str, float]    # single / double / triple / hr / error
    n: int


class SprayChartResponse(BaseModel):
    batter: PlayerSummary
    season: int
    filters_applied: dict[str, Any]
    zones: list[SprayZone]
    logistic_grid: list[list[float]]  # 100×100 hit probability grid
    sample_n: int
    weather_adjusted: bool = False
    park_adjusted: bool = False
    recency_weighted: bool = False  # season=0 totals weighted toward recent seasons


# ─── Range ────────────────────────────────────────────────────────────────────

class PlayerRangeResponse(BaseModel):
    player_id: uuid.UUID
    player_name: str
    position: str
    center_x: float  # normalized 0–1 field coordinates
    center_y: float
    radii: dict[str, float]  # zone_075s / zone_125s / zone_175s / zone_225s / zone_300s
    arm_throw_range: dict[str, float]
    effective_zones: list[int]
    injury_adjusted: bool = False


class TeamRangeResponse(BaseModel):
    fielders: list[PlayerRangeResponse]
    coverage_grid: list[list[float]]
    gap_zones: list[int]
    overlap_zones: list[int]


# ─── Alignments ───────────────────────────────────────────────────────────────

class RosterEntry(BaseModel):
    player_id: uuid.UUID
    position: str
    injury_override: dict[str, float] | None = None


class WeatherInput(BaseModel):
    """Manual/override weather supplied inline with an alignment request.
    Wind direction is meteorological (degrees the wind blows FROM)."""
    temperature_f: float | None = Field(default=None, ge=-20, le=130)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    wind_speed_mph: float | None = Field(default=None, ge=0, le=80)
    wind_direction_deg: float | None = Field(default=None, ge=0, le=360)
    conditions: str | None = None


class AlignmentRequest(BaseModel):
    team_id: uuid.UUID
    batter_id: uuid.UUID
    pitcher_id: uuid.UUID
    stadium_id: uuid.UUID
    weather_id: uuid.UUID | None = None
    weather: WeatherInput | None = None  # inline manual weather (overrides weather_id)
    inning: int | None = Field(default=None, ge=1, le=9)
    outs: int | None = Field(default=None, ge=0, le=2)
    runners: dict[str, bool] = Field(
        default={"on_1b": False, "on_2b": False, "on_3b": False}
    )
    score_diff: int | None = None
    active_roster: list[RosterEntry] = Field(default_factory=list)
    optimize_for: Literal["prevent_hit", "prevent_extra_base", "balanced"] = "balanced"
    include_factors: list[str] = Field(
        default=["pitcher_type", "batter_spray", "weather", "stadium", "injury"]
    )


class FielderPosition(BaseModel):
    player_id: uuid.UUID
    player_name: str
    x: float
    y: float
    depth_ft: float
    angle_deg: float
    catch_prob_zone: float


class AlignmentSummary(BaseModel):
    shift_type: str
    predicted_oaa_delta: float
    predicted_hit_pct: float
    confidence: float


class AlignmentResponse(BaseModel):
    """Alignment recommendation.

    Probability semantics (see documentation/TRUST_REPORT.md, 2026-09-03):
    ``predicted_oaa_delta`` = P(out | this alignment) − P(out | standard) on
    the calibrated per-ball surface; its DIRECTION is outcome-validated
    (EXPERIMENTS.md P1 Part 1), its magnitude is approximate. The absolute
    ``predicted_out_pct``/``predicted_hit_pct`` are calibrated at the
    POPULATION level only (mean bias +0.005 under the empirical landing
    density, ``landing_source="batter"``/"league"): read them as "roughly the
    league out rate, adjusted for this alignment/weather/mix", NOT as a
    batter-specific probability — batter-to-batter variation in them carries
    no validated signal and must not be used to rank batters (EXPERIMENTS.md
    2026-09-03, empirical-density entry). Estimand excludes home runs.
    ``calibrator_version`` names the coverage→P(out) map; null ⇒ raw legacy
    score, never a probability. ``landing_source="spray"`` ⇒ legacy Gaussian
    density with a known +0.055 high bias.
    """
    alignment_id: uuid.UUID
    shift_type: str
    fielder_positions: dict[str, FielderPosition]
    coverage_map: list[list[float]]
    overlap_zones: list[dict[str, Any]]
    predicted_oaa_delta: float
    predicted_hit_pct: float
    predicted_out_pct: float
    confidence: float
    optimize_for: str
    factors_applied: list[str]
    alternatives: list[AlignmentSummary]
    created_at: datetime
    # Pitcher context behind the "pitcher_type" factor (null when not applied)
    pitcher_type: str | None = None
    pitcher_groundball_pct: float | None = None
    # Fly-ball carry multiplier applied for weather (null when no weather)
    weather_carry: float | None = None
    # Version of the out-probability calibrator applied (null = raw, uncalibrated)
    calibrator_version: str | None = None
    # Landing density behind the expectation: "batter" (empirical histogram),
    # "league" (no batter history — league prior), "spray" (legacy Gaussian model)
    landing_source: str | None = None


class AlignmentHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    shift_type: str
    batter_id: uuid.UUID | None
    pitcher_id: uuid.UUID | None
    inning: int | None
    outs: int | None
    fielder_positions: dict[str, Any] | None
    predicted_oaa_delta: float | None
    predicted_hit_pct: float | None
    confidence: float | None
    optimize_for: str
    created_at: datetime


class CustomPosition(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class AlignmentScoreRequest(BaseModel):
    """Score an exact user-arranged alignment (e.g. after dragging fielders)."""
    batter_id: uuid.UUID
    positions: dict[str, CustomPosition]  # position code -> coords
    active_roster: list[RosterEntry] = Field(default_factory=list)
    weather_id: uuid.UUID | None = None
    weather: WeatherInput | None = None  # inline manual weather (overrides weather_id)
    stadium_id: uuid.UUID | None = None
    season: int = 2024
    optimize_for: Literal["prevent_hit", "prevent_extra_base", "balanced"] = "balanced"


class AlignmentScoreResponse(BaseModel):
    """Score for a user-arranged alignment. Same probability semantics as
    AlignmentResponse: the delta's direction is validated; absolute hit/out
    percentages are population-level calibrated only — not batter-specific
    (documentation/TRUST_REPORT.md 2026-09-03)."""
    shift_type: str
    predicted_oaa_delta: float
    predicted_hit_pct: float
    predicted_out_pct: float
    confidence: float
    legal: bool
    illegal_positions: list[str]
    calibrator_version: str | None = None
    landing_source: str | None = None


# ─── Injuries ─────────────────────────────────────────────────────────────────

# Default degradation factors per severity — applied when the client doesn't
# send explicit factors
INJURY_SEVERITY_PRESETS: dict[str, dict[str, float]] = {
    "mild": {"speed": 0.95, "reaction": 0.97, "range": 0.95, "arm_strength": 0.97, "arm_accuracy": 0.98},
    "moderate": {"speed": 0.85, "reaction": 0.90, "range": 0.85, "arm_strength": 0.90, "arm_accuracy": 0.93},
    "severe": {"speed": 0.70, "reaction": 0.80, "range": 0.70, "arm_strength": 0.75, "arm_accuracy": 0.85},
}


class InjuryCreate(BaseModel):
    body_part: str = Field(min_length=2, max_length=50)
    severity: Literal["mild", "moderate", "severe"]
    notes: str | None = Field(default=None, max_length=500)
    # Explicit factors override the severity preset
    speed_factor: float | None = Field(default=None, gt=0, le=1)
    reaction_factor: float | None = Field(default=None, gt=0, le=1)
    range_factor: float | None = Field(default=None, gt=0, le=1)
    arm_strength_factor: float | None = Field(default=None, gt=0, le=1)
    arm_accuracy_factor: float | None = Field(default=None, gt=0, le=1)


class InjuryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    player_id: uuid.UUID
    body_part: str
    severity: str
    active: bool
    start_date: date | None
    end_date: date | None
    speed_factor: float
    reaction_factor: float
    range_factor: float
    arm_strength_factor: float
    arm_accuracy_factor: float
    notes: str | None


# ─── Park layout ──────────────────────────────────────────────────────────────

class WallPoint(BaseModel):
    angle_deg: float
    distance_ft: float
    x: float
    y: float


class DistanceMarker(BaseModel):
    key: str
    label: str
    distance_ft: int
    x: float
    y: float


class FeatureWall(BaseModel):
    key: str
    height_ft: float
    label: str


class StadiumLayoutResponse(BaseModel):
    stadium_id: uuid.UUID
    name: str
    city: str
    state: str | None
    roof_type: str
    surface: str
    altitude_ft: float
    dimensions: dict[str, int]
    wall_points: list[WallPoint]
    distance_markers: list[DistanceMarker]
    feature_walls: list[FeatureWall]
    features: list[str]
    precision: str


# ─── Weather ──────────────────────────────────────────────────────────────────

class GameWeatherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    game_id: str
    stadium_id: uuid.UUID | None
    game_date: date
    temperature_f: float | None
    humidity_pct: float | None
    wind_speed_mph: float | None
    wind_direction_label: str | None
    wind_speed_level: int | None
    conditions: str | None
    wind_x_component: float | None
    wind_y_component: float | None


class WeatherEffectResponse(BaseModel):
    """Preview of how a set of weather conditions will bend batted balls,
    without running a full alignment — drives the manual weather panel."""
    wind_x_component: float   # + = drift toward right field
    wind_y_component: float   # + = blowing out toward the outfield
    wind_direction_label: str | None
    wind_speed_level: int | None
    carry_factor: float       # fly-ball distance multiplier (1.0 = neutral)
    carry_pct: float          # (carry_factor - 1) * 100, for display
    summary: str              # e.g. "Carries well (+6%), drift to RF"


# ─── Ingest ───────────────────────────────────────────────────────────────────

class IngestJobResponse(BaseModel):
    job_id: str
    source: str
    status: str
    started_at: datetime


class IngestJobStatus(BaseModel):
    job_id: str
    status: Literal["pending", "running", "complete", "failed"]
    source: str
    records_processed: int
    errors: list[str]
    started_at: datetime
    finished_at: datetime | None = None


# ─── Stadium ──────────────────────────────────────────────────────────────────

class StadiumResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    mlb_venue_id: str
    name: str
    city: str
    state: str | None
    altitude_ft: float
    roof_type: str
    surface: str
    outfield_acres: float | None
    left_line_ft: float | None
    center_ft: float | None
    right_line_ft: float | None
    park_factor_runs: float
    park_factor_hr: float
