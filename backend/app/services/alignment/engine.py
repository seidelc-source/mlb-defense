"""
Alignment engine — three-stage pipeline:
  1. logistic — produce hit probability grid(s) from batter spray profile
  2. range model — compute fielder reach radii from adjusted profile
  3. scoring — score candidate alignments (with legality + local search), return top-N
"""
from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.config import get_settings
from app.models.remaining_models import BatterSprayProfile, GameWeather
from app.schemas.schemas import FielderPosition

logger = logging.getLogger(__name__)
settings = get_settings()

GRID = settings.alignment_grid_size  # 100×100

INFIELD = ("1B", "2B", "SS", "3B")
OUTFIELD = ("LF", "CF", "RF")

# MLB shift restrictions (2023+): all four infielders must be on the infield
# dirt with two entirely on each side of second base at pitch release.
# In normalized coords second base sits at x=0.5; the dirt extends to y≈0.45.
SECOND_BASE_X = 0.5
INFIELD_MIN_Y = 0.18
INFIELD_MAX_Y = 0.45
LEGAL_MARGIN = 0.01  # "entirely on one side" buffer


# ── Logistic (spray → probability grid) ──────────────────────────────────────

# Map zone 1–8 to approximate normalized field coordinates (center x, y)
# y=0 is home plate, y=1 is center-field wall
# x=0 is left field line, x=1 is right field line
ZONE_CENTERS: dict[int, tuple[float, float]] = {
    1: (0.65, 0.30),  # first base area
    2: (0.55, 0.35),  # second base area
    3: (0.45, 0.35),  # shortstop area
    4: (0.35, 0.30),  # third base area
    5: (0.20, 0.70),  # left field
    6: (0.35, 0.80),  # left-center
    7: (0.65, 0.80),  # right-center
    8: (0.80, 0.70),  # right field
}

# Zone "spread" — how wide each zone is in normalized coords
ZONE_SIGMA: dict[int, float] = {
    1: 0.08, 2: 0.08, 3: 0.08, 4: 0.08,
    5: 0.12, 6: 0.12, 7: 0.12, 8: 0.12,
}


# ── Weather effect on batted-ball location ───────────────────────────────────

def carry_factor(weather: GameWeather | None, altitude_ft: float = 0.0) -> float:
    """Multiplier (~0.85–1.20) on fly-ball carry distance from air density and
    wind. 1.0 = neutral (70°F, sea level, ~50% humidity, calm). Hot air, high
    elevation, thin/humid air, and a wind blowing out all push it above 1.0;
    cold air and a wind blowing in pull it below."""
    if weather is None:
        return 1.0
    temp = weather.temperature_f if weather.temperature_f is not None else 70.0
    humidity = weather.humidity_pct if weather.humidity_pct is not None else 50.0
    wind_out = weather.wind_y_component or 0.0   # + = blowing toward the outfield
    f = 1.0
    f += (temp - 70.0) * 0.0007             # ~0.7% per 10°F
    f += (altitude_ft / 1000.0) * 0.012     # ~1.2% per 1,000 ft of elevation
    f += (humidity - 50.0) / 50.0 * 0.005   # humid air is slightly less dense
    f += wind_out * 0.006                    # ~0.6% per mph blowing out (− when in)
    return max(0.85, min(1.20, f))


# Per-trajectory response to wind (lateral) and carry (depth), in grid cells.
# Grounders barely move through the air; fly balls drift and carry the most.
_LATERAL_SCALE = {"ground": 0.1, "air": 0.6, None: 0.5}
_DEPTH_SCALE = {"ground": 0.0, "air": 0.7, None: 0.0}


def _weather_shift(
    weather: GameWeather, trajectory: str | None, altitude_ft: float
) -> tuple[int, int]:
    """(shift_x, shift_y) in grid cells: crosswind drift + carry depth."""
    shift_x = int(round((weather.wind_x_component or 0.0) * _LATERAL_SCALE.get(trajectory, 0.5)))
    depth_scale = _DEPTH_SCALE.get(trajectory, 0.0)
    shift_y = (
        int(round((carry_factor(weather, altitude_ft) - 1.0) * GRID * depth_scale))
        if depth_scale
        else 0
    )
    return shift_x, shift_y


def build_hit_probability_grid(
    spray_zones: list[BatterSprayProfile],
    weather: GameWeather | None = None,
    trajectory: str | None = None,
    altitude_ft: float = 0.0,
) -> np.ndarray:
    """
    Return a (GRID×GRID) float32 array where each cell contains the
    estimated probability that a batted ball lands in that field location
    as a hit.

    trajectory: None → all batted balls; "ground" → weight by groundball share;
    "air" → weight by flyball+linedrive+popup share. Weather drifts fly balls
    laterally (crosswind) and deepens/shortens them (carry from temp, elevation,
    humidity, and a wind blowing out/in); grounders are largely unaffected.
    """
    grid = np.zeros((GRID, GRID), dtype=np.float32)

    if not spray_zones:
        # No data — return uniform distribution as fallback
        return grid + (1.0 / (GRID * GRID))

    xs = np.linspace(0, 1, GRID)
    ys = np.linspace(0, 1, GRID)
    xv, yv = np.meshgrid(xs, ys)

    for zone_row in spray_zones:
        z = zone_row.fielding_zone
        if z not in ZONE_CENTERS:
            continue
        cx, cy = ZONE_CENTERS[z]
        sigma = ZONE_SIGMA[z]

        # Weight by hit probability for this zone
        weight = zone_row.hit_pct * zone_row.sample_n
        if trajectory == "ground":
            weight *= zone_row.groundball_pct
        elif trajectory == "air":
            weight *= (
                zone_row.flyball_pct + zone_row.linedrive_pct + zone_row.popup_pct
            )
        if weight <= 0:
            continue

        # Gaussian blob centered on zone
        blob = np.exp(
            -((xv - cx) ** 2 + (yv - cy) ** 2) / (2 * sigma**2)
        ).astype(np.float32)
        grid += blob * weight

    # Apply weather: crosswind drift (x) + carry depth (y), trajectory-aware
    if weather is not None:
        shift_x, shift_y = _weather_shift(weather, trajectory, altitude_ft)
        if shift_x != 0 or shift_y != 0:
            grid = np.roll(grid, shift_x, axis=1)
            grid = np.roll(grid, shift_y, axis=0)

    # Normalise to [0, 1]
    total = grid.sum()
    if total > 0:
        grid = grid / total

    return grid


# ── Range model (fielder reach radii) ────────────────────────────────────────

@dataclass
class FielderReach:
    player_id: uuid.UUID
    position: str
    center_x: float
    center_y: float
    # Time-to-reach radii in normalized field units
    r_075s: float = 0.06
    r_125s: float = 0.10
    r_175s: float = 0.14
    r_225s: float = 0.18
    r_300s: float = 0.22

    def coverage_grid(self) -> np.ndarray:
        """Return a GRID×GRID catch-probability surface for this fielder."""
        xs = np.linspace(0, 1, GRID)
        ys = np.linspace(0, 1, GRID)
        xv, yv = np.meshgrid(xs, ys)
        dist = np.sqrt((xv - self.center_x) ** 2 + (yv - self.center_y) ** 2)
        # Catch probability decays linearly from 1.0 at center to 0 at r_300s
        prob = np.clip(1.0 - dist / self.r_300s, 0.0, 1.0)
        return prob.astype(np.float32)

    def at(self, cx: float, cy: float) -> "FielderReach":
        """Same fielder, different position."""
        return FielderReach(
            player_id=self.player_id, position=self.position,
            center_x=cx, center_y=cy,
            r_075s=self.r_075s, r_125s=self.r_125s, r_175s=self.r_175s,
            r_225s=self.r_225s, r_300s=self.r_300s,
        )


def compute_reach(
    player_id: uuid.UUID,
    position: str,
    center_x: float,
    center_y: float,
    sprint_speed: float | None,
    reaction_time: float | None,
    route_efficiency: float | None,
) -> FielderReach:
    """Convert raw fielding attributes into time-based reach radii."""
    # Baseline: average MLB outfielder sprint speed ~27 ft/s
    speed = sprint_speed or 27.0
    rt = reaction_time or 0.4
    re = (route_efficiency or 85.0) / 100.0  # normalize to 0–1

    # Field is ~400ft deep in normalized coordinates → 1 unit ≈ 400ft
    # Time to reach ball = (distance_ft / speed_ft_s) + reaction_time
    # Solving distance for t: d = (t - rt) * speed * route_efficiency
    def radius(t: float) -> float:
        effective_time = max(0.0, t - rt)
        dist_ft = effective_time * speed * re
        return dist_ft / 400.0  # normalize

    return FielderReach(
        player_id=player_id,
        position=position,
        center_x=center_x,
        center_y=center_y,
        r_075s=radius(0.75),
        r_125s=radius(1.25),
        r_175s=radius(1.75),
        r_225s=radius(2.25),
        r_300s=radius(3.00),
    )


# ── Shift heuristics ──────────────────────────────────────────────────────────

# ── Batter handedness (pull-side geometry) ────────────────────────────────────
# Field coords: x=0 is the LF line, x=1 is the RF line, x=0.5 is 2B/CF.
# A LEFT-handed batter pulls to RF (high x); a RIGHT-handed batter pulls to LF
# (low x). The shift heuristics below are written for the canonical "pull = RF"
# case (LH); right-handed batters are handled by reflecting about x=0.5.

# Zone reflection about x=0.5: infield 1↔4, 2↔3; outfield 5↔8, 6↔7.
ZONE_MIRROR: dict[int, int] = {1: 4, 2: 3, 3: 2, 4: 1, 5: 8, 6: 7, 7: 6, 8: 5}

# Position-label swap under x→1-x, chosen so shift legality survives the mirror
# (1B/2B stay right of 2B, SS/3B stay left): 1B↔3B, 2B↔SS, LF↔RF.
_POS_MIRROR: dict[str, str] = {
    "1B": "3B", "3B": "1B", "2B": "SS", "SS": "2B",
    "LF": "RF", "RF": "LF", "CF": "CF", "C": "C", "P": "P",
}


def _pulls_to_rf(bats: str | None) -> bool:
    """True for the canonical case (pull side = RF / high x): left-handed batters
    and the None default. Right-handed batters pull to LF and are mirrored."""
    return bats != "R"


def _mirror_positions(
    positions: dict[str, tuple[float, float]]
) -> dict[str, tuple[float, float]]:
    """Reflect an alignment about x=0.5 and relabel positions so shift legality is
    preserved. Turns a canonical pull-to-RF (LH) alignment into the correct
    pull-to-LF (RH) mirror image. The standard alignment is invariant under this
    (coords rounded to avoid floating-point drift so that invariance is exact)."""
    return {_POS_MIRROR[p]: (round(1.0 - x, 6), y) for p, (x, y) in positions.items()}


def resolve_batter_hand(bats: str | None, pitcher_throws: str | None) -> str | None:
    """Effective batting hand. Switch hitters ("S") bat opposite the pitcher:
    L vs RHP, R vs LHP (default L when the pitcher hand is unknown)."""
    if bats in ("L", "R"):
        return bats
    if bats == "S":
        return "R" if pitcher_throws == "L" else "L"
    return None


def suggest_shift_type(
    spray_zones: list[BatterSprayProfile], bats: str | None = None
) -> str:
    """Heuristic: if >40% of balls go to the pull-side infield zones, suggest an
    infield shift. Pull side depends on batter handedness — zones are reflected
    for right-handed batters so the canonical (pull = RF) logic applies."""
    if not spray_zones:
        return "standard"

    def zone_of(z: BatterSprayProfile) -> int | None:
        return z.fielding_zone if _pulls_to_rf(bats) else ZONE_MIRROR.get(z.fielding_zone)

    total = sum(z.hit_count for z in spray_zones) or 1
    pull_count = sum(z.hit_count for z in spray_zones if zone_of(z) in {1, 2})
    if pull_count / total >= 0.40:
        return "infield_shift"
    oppo_count = sum(z.hit_count for z in spray_zones if zone_of(z) in {7, 8})
    if oppo_count / total >= 0.35:
        return "outfield_shift"
    return "standard"


# ── Default positions (standard alignment) ───────────────────────────────────

STANDARD_POSITIONS: dict[str, tuple[float, float]] = {
    "1B": (0.62, 0.28), "2B": (0.58, 0.38), "SS": (0.42, 0.38), "3B": (0.38, 0.28),
    "LF": (0.18, 0.72), "CF": (0.50, 0.82), "RF": (0.82, 0.72),
    "C":  (0.50, 0.05), "P":  (0.50, 0.18),
}


def default_positions_for_shift(
    shift_type: str, bats: str | None = None
) -> dict[str, tuple[float, float]]:
    """Template alignment for a shift type. Templates are authored for the
    canonical pull-to-RF (LH) batter and reflected about x=0.5 for right-handed
    batters, so the shift is aimed at the batter's actual pull side. The standard
    alignment is invariant under the reflection."""
    positions = STANDARD_POSITIONS.copy()
    if shift_type == "infield_shift":
        # Legal pull-side lean: 2B shades toward 1B, SS shades toward the bag.
        # Two infielders stay on each side of second base (2023+ shift rule).
        # NOTE (2026-09-02): a more aggressive static template was tried and
        # REJECTED — pushing 1B/2B to the RF line and stacking SS/3B left vacated
        # the up-the-middle lane and *reduced* modeled coverage of real grounders
        # (predicted shift lift went negative; see EXPERIMENTS.md). Correct shift
        # magnitude is batter-specific and belongs to per-batter optimization
        # (`optimize_positions`), not a stronger fixed template.
        positions["2B"] = (0.66, 0.36)
        positions["SS"] = (0.48, 0.38)
        positions["3B"] = (0.42, 0.30)
    elif shift_type == "outfield_shift":
        # Shift outfielders toward right
        positions["LF"] = (0.28, 0.72)
        positions["CF"] = (0.60, 0.82)
        positions["RF"] = (0.88, 0.68)
    if not _pulls_to_rf(bats):
        positions = _mirror_positions(positions)
    return positions


# ── Shift legality (MLB 2023+ rules) + park bounds ───────────────────────────

WALL_BUFFER_FT = 15.0  # outfielders position at least this far inside the fence


def _radial_ft(x: float, y: float) -> float:
    """Distance from home plate in feet for a normalized coordinate."""
    return math.hypot(x - 0.5, y) * 400.0


def is_legal_position(
    position: str,
    x: float,
    y: float,
    dimensions: dict[str, int] | None = None,
) -> bool:
    """Check one fielder's spot against shift restrictions and, when park
    dimensions are provided, the outfield fence."""
    if position in ("C", "P"):
        return True
    if position in INFIELD:
        if not (INFIELD_MIN_Y <= y <= INFIELD_MAX_Y):
            return False
        if position in ("1B", "2B"):
            return x >= SECOND_BASE_X + LEGAL_MARGIN
        return x <= SECOND_BASE_X - LEGAL_MARGIN  # SS, 3B
    # Outfielders: unrestricted, but must be in the outfield — and in front
    # of the wall when we know the park.
    if y < INFIELD_MAX_Y:
        return False
    if dimensions is not None:
        from app.services.park_layout import wall_distance_at
        if _radial_ft(x, y) > wall_distance_at(dimensions, x, y) - 5.0:
            return False
    return True


def is_legal_alignment(
    positions: dict[str, tuple[float, float]],
    dimensions: dict[str, int] | None = None,
) -> bool:
    return all(
        is_legal_position(pos, x, y, dimensions) for pos, (x, y) in positions.items()
    )


def clamp_to_legal(
    position: str,
    x: float,
    y: float,
    dimensions: dict[str, int] | None = None,
) -> tuple[float, float]:
    """Snap a fielder's coordinates to the nearest legal spot."""
    # With park dimensions the fence is the real outer bound; corner walls
    # legitimately sit slightly outside the unit square.
    if position in OUTFIELD and dimensions is not None:
        x = min(max(x, -0.1), 1.1)
        y = min(max(y, 0.02), 1.1)
    else:
        x = min(max(x, 0.02), 0.98)
        y = min(max(y, 0.02), 0.98)
    if position in INFIELD:
        y = min(max(y, INFIELD_MIN_Y), INFIELD_MAX_Y)
        if position in ("1B", "2B"):
            x = max(x, SECOND_BASE_X + LEGAL_MARGIN)
        else:
            x = min(x, SECOND_BASE_X - LEGAL_MARGIN)
    elif position in OUTFIELD:
        y = max(y, INFIELD_MAX_Y)
        if dimensions is not None:
            from app.services.park_layout import wall_distance_at
            r = _radial_ft(x, y)
            max_r = wall_distance_at(dimensions, x, y) - WALL_BUFFER_FT
            if r > max_r > 0:
                scale = max_r / r
                x = 0.5 + (x - 0.5) * scale
                y = y * scale
    return x, y


# ── Scoring ───────────────────────────────────────────────────────────────────

def _combined_coverage(reaches: list[FielderReach]) -> np.ndarray:
    not_caught = np.ones((GRID, GRID), dtype=np.float32)
    for reach in reaches:
        not_caught *= (1.0 - reach.coverage_grid())
    return 1.0 - not_caught


# Approx MLB share of batted balls hit on the ground; the complement is air.
LEAGUE_GROUND_SHARE = 0.44


def pitcher_trajectory_weights(pitcher_profile: Any | None) -> tuple[float, float]:
    """(ground_weight, air_weight) tilt from a pitcher's groundball tendency.

    Each trajectory grid is normalized independently, so the pitcher's effect
    lives in how heavily ground vs air outs count. A groundball pitcher pushes
    weight toward infield coverage; a flyball pitcher toward the outfield.
    Returns neutral (1.0, 1.0) when no profile / GB rate is available, which
    reproduces the batter-only model exactly. Clamped to a sane range so an
    extreme pitcher can't dominate the batter's own spray tendencies.
    """
    if pitcher_profile is None:
        return 1.0, 1.0
    gb = getattr(pitcher_profile, "groundball_pct", None)
    if gb is None:
        return 1.0, 1.0
    air_share = max(1e-3, 1.0 - gb)
    ground_w = min(1.5, max(0.6, gb / LEAGUE_GROUND_SHARE))
    air_w = min(1.5, max(0.6, air_share / (1.0 - LEAGUE_GROUND_SHARE)))
    return ground_w, air_w


def _expected_outs(
    ground_grid: np.ndarray,
    air_grid: np.ndarray,
    reaches: list[FielderReach],
    optimize_for: str,
    ground_weight: float = 1.0,
    air_weight: float = 1.0,
) -> float:
    """
    Trajectory-aware expected outs: infielders convert ground balls,
    outfielders convert air balls; cross-coverage at reduced weight.
    ``ground_weight``/``air_weight`` tilt the balance by pitcher tendency
    (both 1.0 = batter-only baseline).
    """
    infield = [r for r in reaches if r.position in INFIELD]
    outfield = [r for r in reaches if r.position in OUTFIELD]

    in_cov = _combined_coverage(infield) if infield else np.zeros((GRID, GRID), dtype=np.float32)
    out_cov = _combined_coverage(outfield) if outfield else np.zeros((GRID, GRID), dtype=np.float32)

    # Weights: infield on grounders, outfield on air; cross terms reduced
    ground_outs = float((ground_grid * np.maximum(in_cov, out_cov * 0.15)).sum()) * ground_weight
    air_outs = float((air_grid * np.maximum(out_cov, in_cov * 0.30)).sum()) * air_weight

    if optimize_for == "prevent_extra_base":
        # Deep coverage matters more — upweight air-ball outs
        return 0.7 * ground_outs + 1.3 * air_outs
    if optimize_for == "prevent_hit":
        return 1.2 * ground_outs + 0.9 * air_outs
    return ground_outs + air_outs


def score_alignment(
    hit_prob_grid: np.ndarray,
    fielder_reaches: list[FielderReach],
    optimize_for: str,
) -> tuple[float, float, float]:
    """
    Single-grid scoring (kept for API compatibility).
    Returns (predicted_oaa_delta, predicted_hit_pct, confidence).
    """
    if hit_prob_grid.sum() == 0:
        return 0.0, 0.5, 0.1

    coverage = _combined_coverage(fielder_reaches)
    expected_outs = float((hit_prob_grid * coverage).sum())

    std_reaches = [
        r.at(*STANDARD_POSITIONS.get(r.position, (0.5, 0.5)))
        for r in fielder_reaches
    ]
    std_coverage = _combined_coverage(std_reaches)
    std_expected_outs = float((hit_prob_grid * std_coverage).sum())

    oaa_delta = round(expected_outs - std_expected_outs, 4)
    predicted_hit_pct = round(1.0 - expected_outs, 4)
    confidence = min(1.0, 0.5 + abs(oaa_delta) * 5)

    return oaa_delta, predicted_hit_pct, confidence


def _confidence_from_sample(sample_n: int) -> float:
    """Honest confidence: monotonic in spray sample size."""
    if sample_n <= 0:
        return 0.1
    return round(min(0.95, 0.30 + sample_n / 400.0), 3)


# ── Local search optimization ─────────────────────────────────────────────────

_SEARCH_OFFSETS = [
    (0.03, 0.0), (-0.03, 0.0), (0.0, 0.03), (0.0, -0.03),
    (0.02, 0.02), (0.02, -0.02), (-0.02, 0.02), (-0.02, -0.02),
]


def optimize_positions(
    positions: dict[str, tuple[float, float]],
    reaches_by_pos: dict[str, FielderReach],
    ground_grid: np.ndarray,
    air_grid: np.ndarray,
    optimize_for: str,
    sweeps: int = 2,
    dimensions: dict[str, int] | None = None,
    ground_weight: float = 1.0,
    air_weight: float = 1.0,
) -> dict[str, tuple[float, float]]:
    """
    Greedy local search: nudge each fielder, keep legal improvements.
    """
    current = dict(positions)
    reaches = {
        pos: reach.at(*current[pos])
        for pos, reach in reaches_by_pos.items()
        if pos in current
    }

    def total_outs() -> float:
        return _expected_outs(
            ground_grid, air_grid, list(reaches.values()), optimize_for,
            ground_weight, air_weight,
        )

    best_score = total_outs()

    for _ in range(sweeps):
        improved = False
        for pos in list(reaches.keys()):
            if pos in ("C", "P"):
                continue
            cx, cy = current[pos]
            for dx, dy in _SEARCH_OFFSETS:
                nx, ny = clamp_to_legal(pos, cx + dx, cy + dy, dimensions)
                if (nx, ny) == (cx, cy):
                    continue
                old_reach = reaches[pos]
                reaches[pos] = old_reach.at(nx, ny)
                score = total_outs()
                if score > best_score + 1e-6:
                    best_score = score
                    current[pos] = (nx, ny)
                    cx, cy = nx, ny
                    improved = True
                else:
                    reaches[pos] = old_reach
        if not improved:
            break

    return current


# ── Main engine ───────────────────────────────────────────────────────────────

@dataclass
class AlignmentCandidate:
    shift_type: str
    positions: dict[str, tuple[float, float]]
    oaa_delta: float
    hit_pct: float
    confidence: float
    legal: bool = True


def _build_reaches(
    positions: dict[str, tuple[float, float]],
    fielder_profiles: dict[str, Any],
    roster: dict[str, uuid.UUID],
) -> dict[str, FielderReach]:
    reaches: dict[str, FielderReach] = {}
    for position, (cx, cy) in positions.items():
        if position in ("C", "P"):
            continue
        profile = fielder_profiles.get(position)
        pid = roster.get(position, uuid.uuid4())
        reaches[position] = compute_reach(
            player_id=pid,
            position=position,
            center_x=cx,
            center_y=cy,
            sprint_speed=getattr(profile, "sprint_speed_ft_s", None) if profile else None,
            reaction_time=getattr(profile, "reaction_time_s", None) if profile else None,
            route_efficiency=getattr(profile, "route_efficiency_pct", None) if profile else None,
        )
    return reaches


def compute_alignment(
    spray_zones: list[BatterSprayProfile],
    fielder_profiles: dict[str, Any],  # position -> AdjustedProfile
    roster: dict[str, uuid.UUID],       # position -> player_id
    weather: GameWeather | None,
    optimize_for: str,
    top_n: int,
    dimensions: dict[str, int] | None = None,
    pitcher_profile: Any | None = None,
    altitude_ft: float = 0.0,
    bats: str | None = None,
) -> list[AlignmentCandidate]:
    """
    Core engine: evaluate standard + shift variants + locally-optimized
    placement, return top-N candidates (all legal under 2023+ shift rules
    and inside the park's fence when dimensions are given). When a pitcher
    profile is supplied, its groundball tendency tilts ground-vs-air coverage;
    weather (with stadium altitude) drifts and deepens fly balls. ``bats``
    (effective batting hand 'L'/'R') aims shift templates at the batter's pull
    side; None keeps the canonical (LH/RF) geometry.
    """
    ground_grid = build_hit_probability_grid(spray_zones, weather, trajectory="ground", altitude_ft=altitude_ft)
    air_grid = build_hit_probability_grid(spray_zones, weather, trajectory="air", altitude_ft=altitude_ft)
    ground_weight, air_weight = pitcher_trajectory_weights(pitcher_profile)
    shift_type = suggest_shift_type(spray_zones, bats)
    sample_n = sum(z.sample_n for z in spray_zones) if spray_zones else 0
    confidence = _confidence_from_sample(sample_n)

    def park_clamped(positions: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
        if dimensions is None:
            return positions
        return {
            pos: clamp_to_legal(pos, x, y, dimensions) if pos not in ("C", "P") else (x, y)
            for pos, (x, y) in positions.items()
        }

    # Standard benchmark
    std_positions = park_clamped(default_positions_for_shift("standard", bats))
    std_reaches = _build_reaches(std_positions, fielder_profiles, roster)
    std_outs = _expected_outs(
        ground_grid, air_grid, list(std_reaches.values()), optimize_for,
        ground_weight, air_weight,
    )

    def evaluate(name: str, positions: dict[str, tuple[float, float]]) -> AlignmentCandidate:
        reaches = _build_reaches(positions, fielder_profiles, roster)
        outs = _expected_outs(
            ground_grid, air_grid, list(reaches.values()), optimize_for,
            ground_weight, air_weight,
        )
        return AlignmentCandidate(
            shift_type=name,
            positions=positions,
            oaa_delta=round(outs - std_outs, 4),
            hit_pct=round(max(0.0, 1.0 - outs), 4),
            confidence=confidence,
            legal=is_legal_alignment(positions, dimensions),
        )

    candidate_names = dict.fromkeys(["standard", shift_type, "outfield_shift"])
    candidates = [
        evaluate(name, park_clamped(default_positions_for_shift(name, bats)))
        for name in candidate_names
    ]

    # Locally optimize from the best heuristic candidate
    best_so_far = max(candidates, key=lambda c: c.oaa_delta)
    reaches_by_pos = _build_reaches(best_so_far.positions, fielder_profiles, roster)
    optimized_positions = optimize_positions(
        {k: v for k, v in best_so_far.positions.items()},
        reaches_by_pos,
        ground_grid,
        air_grid,
        optimize_for,
        dimensions=dimensions,
        ground_weight=ground_weight,
        air_weight=air_weight,
    )
    optimized = evaluate("optimized", optimized_positions)
    if optimized.oaa_delta > best_so_far.oaa_delta + 1e-6:
        candidates.append(optimized)

    # Sort by oaa_delta descending (better = more outs above average)
    candidates.sort(key=lambda c: c.oaa_delta, reverse=True)
    return candidates[:top_n]


def score_custom_positions(
    custom_positions: dict[str, tuple[float, float]],
    spray_zones: list[BatterSprayProfile],
    fielder_profiles: dict[str, Any],
    roster: dict[str, uuid.UUID],
    weather: GameWeather | None,
    optimize_for: str,
    dimensions: dict[str, int] | None = None,
    pitcher_profile: Any | None = None,
    altitude_ft: float = 0.0,
    bats: str | None = None,
) -> AlignmentCandidate:
    """
    Score an exact user-supplied arrangement (e.g. from dragging fielders)
    against the standard benchmark. Does not move any fielder.
    """
    ground_grid = build_hit_probability_grid(spray_zones, weather, trajectory="ground", altitude_ft=altitude_ft)
    air_grid = build_hit_probability_grid(spray_zones, weather, trajectory="air", altitude_ft=altitude_ft)
    ground_weight, air_weight = pitcher_trajectory_weights(pitcher_profile)
    sample_n = sum(z.sample_n for z in spray_zones) if spray_zones else 0

    std_positions = default_positions_for_shift("standard", bats)
    std_reaches = _build_reaches(std_positions, fielder_profiles, roster)
    std_outs = _expected_outs(
        ground_grid, air_grid, list(std_reaches.values()), optimize_for,
        ground_weight, air_weight,
    )

    reaches = _build_reaches(custom_positions, fielder_profiles, roster)
    outs = _expected_outs(
        ground_grid, air_grid, list(reaches.values()), optimize_for,
        ground_weight, air_weight,
    )

    return AlignmentCandidate(
        shift_type="custom",
        positions=custom_positions,
        oaa_delta=round(outs - std_outs, 4),
        hit_pct=round(max(0.0, 1.0 - outs), 4),
        confidence=_confidence_from_sample(sample_n),
        legal=is_legal_alignment(custom_positions, dimensions),
    )
