"""Feature store - materialiserade features för ML.

Bor i features-schemat för att hålla det skilt från råa data. Byggs om
från grunden vid varje pipeline-körning genom att läsa transaktionsdatan
från public-schemat.
"""

import uuid
from datetime import date as DateType  # noqa: N812
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from travai.db.base import Base, TimestampMixin, UUIDPrimaryKey

FEATURES_SCHEMA = "features"


class HorseFormSnapshot(Base, UUIDPrimaryKey, TimestampMixin):
    """Snapshot av en hästs form vid en given tidpunkt.

    Materialiseras för snabb feature-läsning vid prediktion.
    """

    __tablename__ = "horse_form_snapshots"
    __table_args__ = (
        Index("ix_horse_form_horse_date", "horse_id", "snapshot_date"),
        {"schema": FEATURES_SCHEMA},
    )

    horse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("horses.id"), nullable=False)
    snapshot_date: Mapped[DateType] = mapped_column(Date, nullable=False)

    starts_30d: Mapped[int | None] = mapped_column(Integer)
    starts_90d: Mapped[int | None] = mapped_column(Integer)
    starts_365d: Mapped[int | None] = mapped_column(Integer)
    wins_30d: Mapped[int | None] = mapped_column(Integer)
    wins_90d: Mapped[int | None] = mapped_column(Integer)
    wins_365d: Mapped[int | None] = mapped_column(Integer)
    placed_30d: Mapped[int | None] = mapped_column(Integer)
    placed_90d: Mapped[int | None] = mapped_column(Integer)
    placed_365d: Mapped[int | None] = mapped_column(Integer)
    best_km_time_90d: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    avg_finish_position_5last: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    earnings_per_start_career_minor: Mapped[int | None] = mapped_column(BigInteger)


class TrackPostPositionStats(Base, UUIDPrimaryKey, TimestampMixin):
    """Hur ofta vinner spår X på en given bana över olika distanser."""

    __tablename__ = "track_post_position_stats"
    __table_args__ = (
        Index("ix_track_pp_track_distance", "track_id", "distance_m"),
        {"schema": FEATURES_SCHEMA},
    )

    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    distance_m: Mapped[int] = mapped_column(Integer, nullable=False)
    post_position: Mapped[int] = mapped_column(Integer, nullable=False)
    samples: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    place_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)


class PersonRollingStats(Base, UUIDPrimaryKey, TimestampMixin):
    """Rullande statistik för kuskar/tränare per dag.

    Materialiseras dagligen för snabb lookup vid prediktion.
    """

    __tablename__ = "person_rolling_stats"
    __table_args__ = (
        Index("ix_person_rolling_person_date_role", "person_id", "snapshot_date", "role"),
        {"schema": FEATURES_SCHEMA},
    )

    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id"), nullable=False)
    snapshot_date: Mapped[DateType] = mapped_column(Date, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    drives_30d: Mapped[int | None] = mapped_column(Integer)
    wins_30d: Mapped[int | None] = mapped_column(Integer)
    win_rate_30d: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    drives_90d: Mapped[int | None] = mapped_column(Integer)
    wins_90d: Mapped[int | None] = mapped_column(Integer)
    win_rate_90d: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))


class StartFeatures(Base, TimestampMixin):
    """Materialiserade features per start - en rad per start.

    Det här är input-tabellen för ML-träning och inferens. Alla värden är
    "leak-fria": de räknas från data som var känd före loppets start.

    Cross-validation över tid:
    - Träna: race_date < 2024-01-01
    - Validera: 2024-01-01 <= race_date < 2025-01-01
    - Test: race_date >= 2025-01-01
    """

    __tablename__ = "start_features"
    __table_args__ = (
        Index("ix_start_features_race", "race_id"),
        Index("ix_start_features_horse", "horse_id"),
        Index("ix_start_features_race_date", "race_date"),
        {"schema": FEATURES_SCHEMA},
    )

    # Identifierare (start_id är PK, race_id är group-key för LambdaRank)
    start_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("starts.id"), primary_key=True)
    race_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("horses.id"), nullable=False)

    # Tidstämpel (för CV-uppdelning)
    race_date: Mapped[DateType] = mapped_column(Date, nullable=False)

    # ===== Target-variabler =====
    finish_position: Mapped[int | None] = mapped_column(Integer)
    relevance_score: Mapped[int | None] = mapped_column(Integer)
    # relevance: max(0, num_starters - finish_position + 1), 0 om DNF
    # ex: 12 startande, finishar 1:a → relevance=12; finishar 5:a → relevance=8

    # ===== Häst karriär (pre-race) =====
    career_starts_prior: Mapped[int | None] = mapped_column(Integer)
    career_wins_prior: Mapped[int | None] = mapped_column(Integer)
    career_top3_prior: Mapped[int | None] = mapped_column(Integer)
    career_earnings_minor_prior: Mapped[int | None] = mapped_column(BigInteger)
    career_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    career_top3_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))

    # ===== Häst rullande form =====
    starts_30d: Mapped[int | None] = mapped_column(Integer)
    starts_90d: Mapped[int | None] = mapped_column(Integer)
    starts_365d: Mapped[int | None] = mapped_column(Integer)
    wins_30d: Mapped[int | None] = mapped_column(Integer)
    wins_90d: Mapped[int | None] = mapped_column(Integer)
    wins_365d: Mapped[int | None] = mapped_column(Integer)
    top3_30d: Mapped[int | None] = mapped_column(Integer)
    top3_90d: Mapped[int | None] = mapped_column(Integer)

    # ===== Häst tider =====
    avg_finish_pos_last5: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    best_km_time_career: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    best_km_time_90d: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    avg_km_time_last5: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    # ===== Vila & frekvens =====
    days_since_last_start: Mapped[int | None] = mapped_column(Integer)

    # ===== Häst på bana/distans =====
    starts_at_track_prior: Mapped[int | None] = mapped_column(Integer)
    wins_at_track_prior: Mapped[int | None] = mapped_column(Integer)
    starts_at_distance_prior: Mapped[int | None] = mapped_column(Integer)
    # "distance" = inom +-200m

    # ===== Kusk (rider) features =====
    rider_drives_30d: Mapped[int | None] = mapped_column(Integer)
    rider_wins_30d: Mapped[int | None] = mapped_column(Integer)
    rider_drives_90d: Mapped[int | None] = mapped_column(Integer)
    rider_wins_90d: Mapped[int | None] = mapped_column(Integer)
    rider_win_rate_90d: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))

    # ===== Tränare features =====
    trainer_starts_30d: Mapped[int | None] = mapped_column(Integer)
    trainer_wins_30d: Mapped[int | None] = mapped_column(Integer)
    trainer_starts_90d: Mapped[int | None] = mapped_column(Integer)
    trainer_wins_90d: Mapped[int | None] = mapped_column(Integer)
    trainer_win_rate_90d: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))

    # ===== Pedigree (totalt över alla syskon) =====
    father_offspring_wins: Mapped[int | None] = mapped_column(Integer)
    mother_offspring_wins: Mapped[int | None] = mapped_column(Integer)

    # ===== Utrustning (vid detta lopp) =====
    shoes_front: Mapped[bool | None] = mapped_column(Boolean)
    shoes_back: Mapped[bool | None] = mapped_column(Boolean)
    shoes_either_changed: Mapped[bool | None] = mapped_column(Boolean)
    sulky_changed: Mapped[bool | None] = mapped_column(Boolean)

    # ===== Lopp-kontext =====
    num_starters: Mapped[int | None] = mapped_column(Integer)
    post_position: Mapped[int | None] = mapped_column(Integer)
    post_position_normalized: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    horse_age_at_start: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[int | None] = mapped_column(Integer)

    # ===== Oddsbaserade features =====
    final_win_odds: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    log_final_win_odds: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    odds_rank_in_race: Mapped[int | None] = mapped_column(Integer)
    is_favorite: Mapped[bool | None] = mapped_column(Boolean)
    v75_pool_share: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))

    # ===== Tids- och säsongseffekter =====
    month: Mapped[int | None] = mapped_column(Integer)
    day_of_week: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
