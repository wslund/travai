"""Feature store-tabeller i `features`-schemat.

Dessa är materialiserade (beräknade och lagrade) features för
ML-modellen. De byggs upp av ETL-jobb från rådatan i public-schemat.

Anledningen till separat schema är:
- Tydlig logisk separation mellan rå data och beräknad data
- Lätt att TRUNCATE och bygga om utan att röra rådatan
- Lätt att migrera till en separat databas eller en kolumnbutik
  (DuckDB/ClickHouse) senare om volym kräver det

Princip: ALDRIG leakage. Allt här ska vara "vad visste vi vid tidpunkten
T", inte "vad vet vi nu". Annars förstörs träningen.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from travai.db.base import Base, TimestampMixin, UUIDPrimaryKey

FEATURES_SCHEMA = "features"


class HorseFormSnapshot(Base, UUIDPrimaryKey, TimestampMixin):
    """Hästens form vid en specifik start-tidpunkt.

    Beräknas från historiska starter FÖRE start_id:s datum. En rad per start.
    Detta gör träningsdataset extraherbart utan komplicerade window-queries.
    """

    __tablename__ = "horse_form_snapshots"
    __table_args__ = ({"schema": FEATURES_SCHEMA},)

    start_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    horse_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Statistik över senaste N starter
    starts_last_5: Mapped[int | None] = mapped_column(Integer)
    wins_last_5: Mapped[int | None] = mapped_column(Integer)
    places_last_5: Mapped[int | None] = mapped_column(Integer)  # topp-3
    avg_finish_last_5: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    avg_km_time_last_5: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    starts_last_10: Mapped[int | None] = mapped_column(Integer)
    wins_last_10: Mapped[int | None] = mapped_column(Integer)
    places_last_10: Mapped[int | None] = mapped_column(Integer)

    # Karriärsstatistik (livstid fram till as_of_date)
    career_starts: Mapped[int | None] = mapped_column(Integer)
    career_wins: Mapped[int | None] = mapped_column(Integer)
    career_places: Mapped[int | None] = mapped_column(Integer)
    career_win_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    # Dagar sedan senaste start (rest/comeback-indikator)
    days_since_last_start: Mapped[int | None] = mapped_column(Integer)

    # Best km time någonsin
    best_km_time_s: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))


class TrackPostPositionStats(Base, UUIDPrimaryKey, TimestampMixin):
    """Spårbias per (bana, distans, startmetod, spår, datum).

    Rullande statistik som mäter hur ofta spår X vinner på bana Y vid
    distans Z med startmetod W. Beräknas baklänges, t.ex. på sliding
    window om 365 dagar fram till as_of_date.
    """

    __tablename__ = "track_post_position_stats"
    __table_args__ = (
        Index(
            "ix_pp_stats_lookup",
            "track_id",
            "distance_m",
            "start_method",
            "post_position",
            "as_of_date",
            unique=True,
        ),
        {"schema": FEATURES_SCHEMA},
    )

    track_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    distance_m: Mapped[int] = mapped_column(Integer, nullable=False)
    start_method: Mapped[str] = mapped_column(String(30), nullable=False)
    post_position: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)

    total_starts: Mapped[int | None] = mapped_column(Integer)
    wins: Mapped[int | None] = mapped_column(Integer)
    places: Mapped[int | None] = mapped_column(Integer)
    win_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))


class PersonRollingStats(Base, UUIDPrimaryKey, TimestampMixin):
    """Rullande statistik för kuskar/jockeys/tränare.

    `role` skiljer mellan rid- och tränarroll eftersom samma person kan
    ha båda och statistiken skiljer sig markant.
    """

    __tablename__ = "person_rolling_stats"
    __table_args__ = (
        Index(
            "ix_person_stats_lookup",
            "person_id",
            "role",
            "as_of_date",
            "window_days",
            unique=True,
        ),
        {"schema": FEATURES_SCHEMA},
    )

    person_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'rider' or 'trainer'
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)

    total_starts: Mapped[int | None] = mapped_column(Integer)
    wins: Mapped[int | None] = mapped_column(Integer)
    places: Mapped[int | None] = mapped_column(Integer)
    win_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    place_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    # ROI om man satsat 1 enhet på varje ridning till slutoddsen
    roi_to_decimal: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
