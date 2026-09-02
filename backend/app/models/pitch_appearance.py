import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class PitchAppearance(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pitch_appearance"
    __table_args__ = (
        Index("ix_pitch_batter_season", "batter_id", "season"),
        Index("ix_pitch_pitcher_season", "pitcher_id", "season"),
        Index("ix_pitch_game_date", "game_date"),
    )

    mlb_play_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    game_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    inning: Mapped[int] = mapped_column(Integer, nullable=False)
    inning_half: Mapped[str] = mapped_column(String(6), nullable=False)  # top | bottom

    pitcher_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("player.id", ondelete="SET NULL"), nullable=True, index=True
    )
    batter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("player.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stadium_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stadium.id", ondelete="SET NULL"), nullable=True
    )
    home_team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    away_team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Pitch characteristics
    pitch_type: Mapped[str | None] = mapped_column(String(5), nullable=True, index=True)
    pitch_type_label: Mapped[str | None] = mapped_column(String(30), nullable=True)
    release_speed_mph: Mapped[float | None] = mapped_column(Float, nullable=True)
    release_speed_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1–7
    spin_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pfx_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    pfx_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    plate_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    plate_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    zone: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Count / baserunner context
    balls: Mapped[int] = mapped_column(Integer, default=0)
    strikes: Mapped[int] = mapped_column(Integer, default=0)
    outs_when_up: Mapped[int] = mapped_column(Integer, default=0)
    on_1b: Mapped[bool] = mapped_column(Boolean, default=False)
    on_2b: Mapped[bool] = mapped_column(Boolean, default=False)
    on_3b: Mapped[bool] = mapped_column(Boolean, default=False)

    # Batted ball raw
    events: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bb_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    launch_angle: Mapped[float | None] = mapped_column(Float, nullable=True)
    launch_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    hit_distance_sc: Mapped[float | None] = mapped_column(Float, nullable=True)
    hc_x: Mapped[float | None] = mapped_column(Float, nullable=True)  # spray chart coords
    hc_y: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Derived categorical outcomes (paper's Table 2)
    fielding_zone: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1–8
    general_result: Mapped[str | None] = mapped_column(String(5), nullable=True)   # hit | out
    specific_result: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ball_trajectory: Mapped[str | None] = mapped_column(String(15), nullable=True)

    # Statcast categorical fielder alignment at pitch (e.g. "Standard",
    # "Infield shift", "Strategic"). Used by the eval harness to restrict to
    # standard-alignment batted balls; not consumed by the engine.
    if_fielding_alignment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    of_fielding_alignment: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Fielder positions at time of pitch {position: mlbam_id}
    fielder_positions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
