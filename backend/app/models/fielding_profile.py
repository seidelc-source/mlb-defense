import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.player import Player


class FieldingProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "fielding_profile"
    __table_args__ = (
        Index("ix_fielding_profile_player_season_pos", "player_id", "season", "position"),
    )

    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("player.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    position: Mapped[str] = mapped_column(String(5), nullable=False)
    games: Mapped[int] = mapped_column(Integer, default=0)
    innings: Mapped[float] = mapped_column(Float, default=0.0)

    # Speed & range — raw values + paper Table 1 categorical levels
    sprint_speed_ft_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    sprint_speed_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1–4
    range_pct_vs_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_level: Mapped[int | None] = mapped_column(Integer, nullable=True)         # 1–5

    # Reaction & route
    reaction_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    reaction_time_level: Mapped[int | None] = mapped_column(Integer, nullable=True) # 1–4
    route_efficiency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    route_efficiency_level: Mapped[int | None] = mapped_column(Integer, nullable=True) # 1–5

    # Arm
    arm_strength_mph: Mapped[float | None] = mapped_column(Float, nullable=True)
    arm_strength_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1–5
    arm_accuracy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    arm_accuracy_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1–5

    # Statcast composite metrics
    outs_above_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    oaa_back: Mapped[float | None] = mapped_column(Float, nullable=True)
    oaa_in: Mapped[float | None] = mapped_column(Float, nullable=True)
    oaa_left: Mapped[float | None] = mapped_column(Float, nullable=True)
    oaa_right: Mapped[float | None] = mapped_column(Float, nullable=True)
    fielding_run_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    fielder_throwing_runs: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Catcher-specific
    framing_runs: Mapped[float | None] = mapped_column(Float, nullable=True)
    blocking_runs: Mapped[float | None] = mapped_column(Float, nullable=True)
    catcher_throwing_runs: Mapped[float | None] = mapped_column(Float, nullable=True)

    player: Mapped["Player"] = relationship("Player", back_populates="fielding_profiles")

    def __repr__(self) -> str:
        return f"<FieldingProfile player={self.player_id} season={self.season} pos={self.position}>"
