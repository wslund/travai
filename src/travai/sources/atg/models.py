"""Pydantic-modeller för ATG:s API-svar.

Modellerna är medvetet lösa (extra=allow) eftersom vi vill behålla
flexibiliteten att läsa fält som vi ännu inte modellerat. Adaptern
plockar fält direkt från råa dict:ar för det mesta.
"""

from datetime import date as Date  # noqa: N812
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LooseModel(BaseModel):
    """Bas som tillåter okända fält."""

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
    """Ett enskilt lopp inom ett spel."""

    id: str
    number: int | None = None
    name: str | None = None
    distance: int | None = None
    startMethod: str | None = None  # noqa: N815
    starts: list[dict[str, Any]] = Field(default_factory=list)


class Game(LooseModel):
    """Komplett spelinfo från /games/{game_id}."""

    id: str
    type: str | None = None
    status: str | None = None
    date: Date | None = None
    tracks: list[dict[str, Any]] = Field(default_factory=list)
    races: list[Race] = Field(default_factory=list)
