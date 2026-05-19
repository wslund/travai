"""Tävlingsdata - banor, tävlingsdagar, lopp, starter och allt runt dem.

Den centrala delen av schemat. Bygger på principen att kärnfält är
universella men sport-specifika fält tillåts vara NULL för andra sporter.
"""

import uuid
from datetime import date as DateType  # noqa: N812
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from travai.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Track(Base, UUIDPrimaryKey, TimestampMixin):
    """En tävlingsbana."""

    __tablename__ = "tracks"

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), nullable=False)

    timezone: Mapped[str | None] = mapped_column(String(50))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    surface_types: Mapped[list[str] | None] = mapped_column(ARRAY(String(20)))

    notes: Mapped[str | None] = mapped_column(Text)


class Meeting(Base, UUIDPrimaryKey, TimestampMixin):
    """En tävlingsdag på en bana."""

    __tablename__ = "meetings"
    __table_args__ = (
        UniqueConstraint("track_id", "date", "session", name="uq_meeting_track_date_session"),
        Index("ix_meeting_date", "date"),
    )

    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    date: Mapped[DateType] = mapped_column(Date, nullable=False)
    session: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str | None] = mapped_column(String(30))

    currency_code: Mapped[str | None] = mapped_column(String(3))


class Race(Base, UUIDPrimaryKey, TimestampMixin):
    """Ett enskilt lopp inom en meeting."""

    __tablename__ = "races"
    __table_args__ = (
        UniqueConstraint("meeting_id", "number", name="uq_race_meeting_number"),
        Index("ix_race_meeting", "meeting_id"),
        Index("ix_race_discipline_date", "discipline_code"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    discipline_code: Mapped[str] = mapped_column(ForeignKey("disciplines.code"), nullable=False)

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String(500))

    distance_m: Mapped[int | None] = mapped_column(Integer)
    start_method: Mapped[str | None] = mapped_column(String(30))

    scheduled_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str | None] = mapped_column(String(30))

    # Galopp-specifika fält
    surface: Mapped[str | None] = mapped_column(String(20))
    going: Mapped[str | None] = mapped_column(String(30))
    track_condition: Mapped[str | None] = mapped_column(String(30))

    race_class: Mapped[str | None] = mapped_column(String(50))
    age_restriction: Mapped[str | None] = mapped_column(String(50))
    sex_restriction: Mapped[str | None] = mapped_column(String(20))

    total_prize_minor: Mapped[int | None] = mapped_column(BigInteger)
    prize_text: Mapped[str | None] = mapped_column(Text)

    # Resultat-relaterat - victory_margin kan bli långt på handicaplöpningar
    # ("Vunnet säkert med 0,75-huvud-1,5-0,5-hals-kort huvud-..." och liknande)
    victory_margin: Mapped[str | None] = mapped_column(Text)
    scratchings: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))


class Start(Base, UUIDPrimaryKey, TimestampMixin):
    """En hästs deltagande i ett lopp."""

    __tablename__ = "starts"
    __table_args__ = (
        UniqueConstraint("race_id", "horse_id", name="uq_start_race_horse"),
        Index("ix_start_race", "race_id"),
        Index("ix_start_horse", "horse_id"),
        Index("ix_start_rider", "rider_id"),
        Index("ix_start_trainer", "trainer_id"),
    )

    race_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("horses.id"), nullable=False)
    rider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("persons.id"))
    trainer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("persons.id"))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("persons.id"))

    start_number: Mapped[int] = mapped_column(Integer, nullable=False)
    post_position: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[int | None] = mapped_column(Integer)

    horse_age_at_start: Mapped[int | None] = mapped_column(Integer)
    horse_earnings_at_start_minor: Mapped[int | None] = mapped_column(BigInteger)

    is_scratched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    finish_position: Mapped[int | None] = mapped_column(Integer)
    finish_order: Mapped[int | None] = mapped_column(Integer)
    finish_time_s: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    km_time_s: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    lengths_behind_winner: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    prize_money_minor: Mapped[int | None] = mapped_column(BigInteger)

    final_win_odds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    # ===== Trav-specifika fält =====
    sulky_type: Mapped[str | None] = mapped_column(String(30))
    sulky_changed: Mapped[bool | None] = mapped_column(Boolean)
    shoes_front: Mapped[bool | None] = mapped_column(Boolean)
    shoes_back: Mapped[bool | None] = mapped_column(Boolean)
    shoes_front_changed: Mapped[bool | None] = mapped_column(Boolean)
    shoes_back_changed: Mapped[bool | None] = mapped_column(Boolean)

    # ===== Galopp-specifika fält =====
    jockey_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    blinkers_on: Mapped[bool | None] = mapped_column(Boolean)
    tongue_tie_on: Mapped[bool | None] = mapped_column(Boolean)
    saddle_cloth_number: Mapped[int | None] = mapped_column(Integer)

    gear_codes: Mapped[list[str] | None] = mapped_column(ARRAY(String(10)))

    incident_notes: Mapped[str | None] = mapped_column(Text)


class SectionalTime(Base, UUIDPrimaryKey, TimestampMixin):
    """Sektionstider."""

    __tablename__ = "sectional_times"
    __table_args__ = (
        UniqueConstraint("start_id", "checkpoint_m", name="uq_sectional_start_checkpoint"),
        Index("ix_sectional_start", "start_id"),
    )

    start_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("starts.id"), nullable=False)
    checkpoint_m: Mapped[int] = mapped_column(Integer, nullable=False)
    time_from_start_s: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    position: Mapped[int | None] = mapped_column(Integer)


class OddsSnapshot(Base, UUIDPrimaryKey, TimestampMixin):
    """En oddsobservation vid en specifik tidpunkt."""

    __tablename__ = "odds_snapshots"
    __table_args__ = (Index("ix_odds_start_type_time", "start_id", "bet_type_code", "captured_at"),)

    start_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("starts.id"), nullable=False)
    bet_type_code: Mapped[str] = mapped_column(String(20), nullable=False)
    bet_type_operator: Mapped[str] = mapped_column(String(50), nullable=False)

    odds_decimal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    odds_decimal_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    pool_share: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class EquipmentChange(Base, UUIDPrimaryKey, TimestampMixin):
    """Utrustningsförändring."""

    __tablename__ = "equipment_changes"
    __table_args__ = (Index("ix_equipment_start", "start_id"),)

    start_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("starts.id"), nullable=False)
    item: Mapped[str] = mapped_column(String(50), nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class WeatherObservation(Base, UUIDPrimaryKey, TimestampMixin):
    """Väderdata för en meeting."""

    __tablename__ = "weather_observations"
    __table_args__ = (Index("ix_weather_meeting", "meeting_id"),)

    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    wind_speed_ms: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    wind_direction_deg: Mapped[int | None] = mapped_column(Integer)
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    humidity_pct: Mapped[int | None] = mapped_column(Integer)
    conditions: Mapped[str | None] = mapped_column(String(50))


class RawPayload(Base, UUIDPrimaryKey, TimestampMixin):
    """Råa JSON-svar från varje datakälla."""

    __tablename__ = "raw_payloads"
    __table_args__ = (
        Index("ix_raw_source_type_external", "source_code", "entity_type", "external_id"),
        Index("ix_raw_fetched_at", "fetched_at"),
    )

    source_code: Mapped[str] = mapped_column(ForeignKey("data_sources.code"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(500))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
