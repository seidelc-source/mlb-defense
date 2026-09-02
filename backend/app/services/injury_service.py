"""
InjuryService applies active injury degradation factors to a FieldingProfile
without mutating the stored record.  Returns an adjusted copy as a plain dict.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fielding_profile import FieldingProfile
from app.models.remaining_models import PlayerInjury
from app.repositories.repositories import InjuryRepository

logger = logging.getLogger(__name__)


@dataclass
class AdjustedProfile:
    """A FieldingProfile with injury factors applied — not an ORM object."""
    sprint_speed_ft_s: float | None
    sprint_speed_level: int | None
    range_pct_vs_avg: float | None
    range_level: int | None
    reaction_time_s: float | None
    reaction_time_level: int | None
    arm_strength_mph: float | None
    arm_strength_level: int | None
    arm_accuracy_pct: float | None
    arm_accuracy_level: int | None
    outs_above_average: float | None
    fielding_run_value: float | None
    injuries_applied: list[str]

    @classmethod
    def from_profile(cls, profile: FieldingProfile) -> "AdjustedProfile":
        return cls(
            sprint_speed_ft_s=profile.sprint_speed_ft_s,
            sprint_speed_level=profile.sprint_speed_level,
            range_pct_vs_avg=profile.range_pct_vs_avg,
            range_level=profile.range_level,
            reaction_time_s=profile.reaction_time_s,
            reaction_time_level=profile.reaction_time_level,
            arm_strength_mph=profile.arm_strength_mph,
            arm_strength_level=profile.arm_strength_level,
            arm_accuracy_pct=profile.arm_accuracy_pct,
            arm_accuracy_level=profile.arm_accuracy_level,
            outs_above_average=profile.outs_above_average,
            fielding_run_value=profile.fielding_run_value,
            injuries_applied=[],
        )


def _apply(value: float | None, factor: float) -> float | None:
    if value is None:
        return None
    return round(value * factor, 3)


class InjuryService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = InjuryRepository(session)

    async def get_active_injuries(self, player_id: Any) -> list[PlayerInjury]:
        return await self.repo.get_active(player_id)

    def apply_factors(
        self, profile: FieldingProfile, injuries: list[PlayerInjury]
    ) -> AdjustedProfile:
        """
        Apply all active injury degradation factors multiplicatively.
        Multiple injuries stack: 0.9 × 0.85 = 0.765 effective factor.
        """
        adjusted = AdjustedProfile.from_profile(profile)
        if not injuries:
            return adjusted

        # Accumulate factors
        speed_f = reaction_f = range_f = arm_str_f = arm_acc_f = 1.0
        for inj in injuries:
            speed_f *= inj.speed_factor
            reaction_f *= inj.reaction_factor
            range_f *= inj.range_factor
            arm_str_f *= inj.arm_strength_factor
            arm_acc_f *= inj.arm_accuracy_factor
            adjusted.injuries_applied.append(f"{inj.body_part}:{inj.severity}")

        # Apply
        adjusted.sprint_speed_ft_s = _apply(adjusted.sprint_speed_ft_s, speed_f)
        adjusted.range_pct_vs_avg = _apply(adjusted.range_pct_vs_avg, range_f)
        adjusted.reaction_time_s = (
            round(adjusted.reaction_time_s / reaction_f, 3)
            if adjusted.reaction_time_s
            else None
        )
        adjusted.arm_strength_mph = _apply(adjusted.arm_strength_mph, arm_str_f)
        adjusted.arm_accuracy_pct = _apply(adjusted.arm_accuracy_pct, arm_acc_f)

        # Re-derive categorical levels after adjustment
        adjusted.sprint_speed_level = _sprint_level(adjusted.sprint_speed_ft_s)
        adjusted.range_level = _range_level(adjusted.range_pct_vs_avg)

        logger.debug(
            "Injury adjustment applied",
            extra={
                "player_id": str(profile.player_id),
                "injuries": adjusted.injuries_applied,
                "speed_factor": speed_f,
            },
        )
        return adjusted

    async def apply_for_player(
        self, profile: FieldingProfile
    ) -> AdjustedProfile:
        injuries = await self.get_active_injuries(profile.player_id)
        return self.apply_factors(profile, injuries)


# ── Categorical level helpers (paper's Table 1) ───────────────────────────────

def _sprint_level(speed: float | None) -> int | None:
    if speed is None:
        return None
    if speed >= 19:
        return 4
    if speed >= 16:
        return 3
    if speed >= 13:
        return 2
    return 1


def _range_level(pct: float | None) -> int | None:
    if pct is None:
        return None
    if pct >= 81:
        return 5
    if pct >= 61:
        return 4
    if pct >= 41:
        return 3
    if pct >= 21:
        return 2
    return 1
