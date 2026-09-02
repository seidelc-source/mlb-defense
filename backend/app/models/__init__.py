"""Import all models so SQLAlchemy's mapper registry is fully populated
whenever any model is imported via this package."""
from app.models.base import Base
from app.models.fielding_profile import FieldingProfile
from app.models.pitch_appearance import PitchAppearance
from app.models.pitcher_profile import PitcherProfile
from app.models.player import Player
from app.models.remaining_models import (
    BatterSprayProfile,
    DefensiveAlignment,
    GameWeather,
    PlayerInjury,
)
from app.models.stadium import Stadium
from app.models.team import Team

__all__ = [
    "Base",
    "BatterSprayProfile",
    "DefensiveAlignment",
    "FieldingProfile",
    "GameWeather",
    "PitchAppearance",
    "PitcherProfile",
    "Player",
    "PlayerInjury",
    "Stadium",
    "Team",
]
