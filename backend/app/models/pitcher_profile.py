import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.player import Player


class PitcherProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pitcher_profile"
    __table_args__ = (
        Index("ix_pitcher_profile_player_season", "player_id", "season"),
    )

    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("player.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(3), nullable=False)  # SP | RP | CL

    # Paper's pitcher type (groundball / flyball / strikeout / neutral)
    pitcher_type: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")
    groundball_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    flyball_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    linedrive_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    popup_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    strikeout_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    walk_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Velocity
    avg_fastball_mph: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_fastball_mph: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_velocity_mph: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Pitch mix — {"FF": 0.52, "SL": 0.28, "CU": 0.20}
    pitch_mix: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Advanced
    xfip: Mapped[float | None] = mapped_column(Float, nullable=True)
    siera: Mapped[float | None] = mapped_column(Float, nullable=True)
    spin_rate_avg: Mapped[int | None] = mapped_column(Integer, nullable=True)

    player: Mapped["Player"] = relationship("Player", back_populates="pitcher_profiles")
