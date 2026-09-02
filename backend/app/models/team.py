import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.player import Player
    from app.models.stadium import Stadium


class Team(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "team"

    mlb_team_id: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    league: Mapped[str] = mapped_column(String(2), nullable=False)   # "AL" | "NL"
    division: Mapped[str] = mapped_column(String(10), nullable=False) # "East" | "Central" | "West"
    home_stadium_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    players: Mapped[list["Player"]] = relationship("Player", back_populates="team")

    def __repr__(self) -> str:
        return f"<Team {self.abbreviation}>"
