"""
Remaining ORM models:
  - BatterSprayProfile
  - GameWeather
  - DefensiveAlignment
  - PlayerInjury
"""
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.player import Player

from app.models.base import Base, TimestampMixin, UUIDMixin


class BatterSprayProfile(UUIDMixin, TimestampMixin, Base):
    """
    Pre-aggregated zone distributions — built nightly from PitchAppearance.
    Keyed by (player_id, season, pitch_type, pitcher_hand, speed_bin).
    """
    __tablename__ = "batter_spray_profile"
    __table_args__ = (
        Index(
            "ix_spray_player_season_scenario",
            "player_id", "season", "pitch_type", "pitcher_hand",
        ),
    )

    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("player.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)

    # Scenario filters (null = "all")
    pitch_type: Mapped[str | None] = mapped_column(String(5), nullable=True)
    pitcher_hand: Mapped[str | None] = mapped_column(String(1), nullable=True)
    pitch_speed_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    pitch_speed_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    count_state: Mapped[str | None] = mapped_column(String(10), nullable=True)

    fielding_zone: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–8

    # Outcome distributions
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    out_count: Mapped[int] = mapped_column(Integer, default=0)
    total_batted_balls: Mapped[int] = mapped_column(Integer, default=0)
    hit_pct: Mapped[float] = mapped_column(Float, default=0.0)
    out_pct: Mapped[float] = mapped_column(Float, default=0.0)

    # Trajectory breakdown
    groundball_pct: Mapped[float] = mapped_column(Float, default=0.0)
    flyball_pct: Mapped[float] = mapped_column(Float, default=0.0)
    linedrive_pct: Mapped[float] = mapped_column(Float, default=0.0)
    popup_pct: Mapped[float] = mapped_column(Float, default=0.0)

    # Specific result breakdown
    single_pct: Mapped[float] = mapped_column(Float, default=0.0)
    double_pct: Mapped[float] = mapped_column(Float, default=0.0)
    triple_pct: Mapped[float] = mapped_column(Float, default=0.0)
    hr_pct: Mapped[float] = mapped_column(Float, default=0.0)
    error_pct: Mapped[float] = mapped_column(Float, default=0.0)

    sample_n: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GameWeather(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "game_weather"
    __table_args__ = (
        Index("ix_game_weather_game_id", "game_id"),
    )

    game_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    stadium_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stadium.id", ondelete="SET NULL"), nullable=True
    )
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    game_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_pitch_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    temperature_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_mph: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_label: Mapped[str | None] = mapped_column(String(3), nullable=True)
    wind_speed_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1–5
    pressure_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    conditions: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Decomposed for alignment engine
    wind_x_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_y_component: Mapped[float | None] = mapped_column(Float, nullable=True)


class DefensiveAlignment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "defensive_alignment"
    __table_args__ = (
        Index("ix_alignment_batter_pitcher", "batter_id", "pitcher_id"),
    )

    alignment_type: Mapped[str] = mapped_column(String(20), nullable=False, default="recommendation")
    game_id: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Scenario FK
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team.id", ondelete="SET NULL"), nullable=True
    )
    batter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("player.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pitcher_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("player.id", ondelete="SET NULL"), nullable=True
    )
    stadium_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stadium.id", ondelete="SET NULL"), nullable=True
    )
    weather_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_weather.id", ondelete="SET NULL"), nullable=True
    )

    # Game state
    inning: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    on_1b: Mapped[bool] = mapped_column(Boolean, default=False)
    on_2b: Mapped[bool] = mapped_column(Boolean, default=False)
    on_3b: Mapped[bool] = mapped_column(Boolean, default=False)
    score_diff: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Shift type
    shift_type: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")

    # Positions — {position: {player_id, x, y, depth_ft, angle_deg}}
    fielder_positions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Model outputs
    predicted_oaa_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_hit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_out_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Metadata
    factors_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    optimize_for: Mapped[str] = mapped_column(String(25), default="balanced", nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), default="0.1.0", nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PlayerInjury(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "player_injury"
    __table_args__ = (
        Index("ix_injury_player_active", "player_id", "active"),
    )

    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("player.id", ondelete="CASCADE"), nullable=False, index=True
    )

    player: Mapped["Player"] = relationship("Player", back_populates="injuries")

    body_part: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # mild | moderate | severe
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_return: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Multiplicative degradation factors (1.0 = full ability)
    speed_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    arm_strength_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    arm_accuracy_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    reaction_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    range_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
