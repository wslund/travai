"""Alla databasmodeller, importerade här så de registreras på Base.metadata."""

from travai.db.models.competitions import (
    EquipmentChange,
    Meeting,
    OddsSnapshot,
    Race,
    RawPayload,
    SectionalTime,
    Start,
    Track,
    WeatherObservation,
)
from travai.db.models.features import (
    FEATURES_SCHEMA,
    HorseFormSnapshot,
    PersonRollingStats,
    TrackPostPositionStats,
)
from travai.db.models.identity import ExternalId, Horse, Person
from travai.db.models.reference import BetType, Country, DataSource, Discipline

__all__ = [
    "FEATURES_SCHEMA",
    "BetType",
    "Country",
    "DataSource",
    "Discipline",
    "EquipmentChange",
    "ExternalId",
    "Horse",
    "HorseFormSnapshot",
    "Meeting",
    "OddsSnapshot",
    "Person",
    "PersonRollingStats",
    "Race",
    "RawPayload",
    "SectionalTime",
    "Start",
    "Track",
    "TrackPostPositionStats",
    "WeatherObservation",
]
