"""Pydantic-modeller för ATG:s API-svar.

I detta läge håller vi modellerna medvetet lösa (extra=allow) eftersom
vi fortfarande utforskar strukturen. När vi vet exakt vilka fält vi
behöver låser vi typningen.
"""

from datetime import date as Date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LooseModel(BaseModel):
    """Bas som tillåter okända fält - för utforskning."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class GameRef(LooseModel):
    """Referens till ett spel/lopp på en given dag."""

    id: str
    status: str | None = None
    track: dict[str, Any] | None = None


class CalendarDay(LooseModel):
    """Svar från /calendar/day/YYYY-MM-DD."""

    games: dict[str, list[GameRef]] = Field(default_factory=dict)
    tracks: list[dict[str, Any]] = Field(default_factory=list)


class Race(LooseModel):
    """Ett enskilt lopp inom ett spel (t.ex. en avdelning av V75)."""

    id: str
    number: int | None = None
    name: str | None = None
    distance: int | None = None
    startMethod: str | None = None
    starts: list[dict[str, Any]] = Field(default_factory=list)


class Game(LooseModel):
    """Komplett spelinfo från /games/{game_id}."""

    id: str
    type: str | None = None
    status: str | None = None
    date: Date | None = None
    tracks: list[dict[str, Any]] = Field(default_factory=list)
    races: list[Race] = Field(default_factory=list)
