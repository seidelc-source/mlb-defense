import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.fielding_profile import FieldingProfile
    from app.models.pitcher_profile import PitcherProfile
    from app.models.player_injury import PlayerInjury
    from app.models.team import Team


class Player(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "player"

    # Cross-source identifiers
    mlbam_id: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    fangraphs_id: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    bbref_id: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    lahman_id: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Identity
    full_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Physical / handedness
    position: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    throws: Mapped[str] = mapped_column(String(1), nullable=False)  # L | R | S
    bats: Mapped[str] = mapped_column(String(1), nullable=False)    # L | R | S
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_country: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pro_debut: Mapped[date | None] = mapped_column(Date, nullable=True)

    # FK
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    team: Mapped["Team | None"] = relationship("Team", back_populates="players")
    fielding_profiles: Mapped[list["FieldingProfile"]] = relationship(
        "FieldingProfile", back_populates="player", cascade="all, delete-orphan"
    )
    pitcher_profiles: Mapped[list["PitcherProfile"]] = relationship(
        "PitcherProfile", back_populates="player", cascade="all, delete-orphan"
    )
    injuries: Mapped[list["PlayerInjury"]] = relationship(
        "PlayerInjury", back_populates="player", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Player {self.full_name} ({self.position})>"
