"""Universella identiteter för hästar och personer + extern ID-mappning.

`persons` och `horses` har interna UUID:er. När en datakälla refererar till
samma entitet med sin egen ID, mappar vi det via `external_ids`.

Detsamma kan upprepas över flera källor - en franskt född häst som tävlat
i Sverige, Frankrike och Hong Kong får tre rader i external_ids men en
rad i horses.
"""

import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from travai.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Horse(Base, UUIDPrimaryKey, TimestampMixin):
    """Universell tävlingshäst.

    Pedigree är self-referencing - far och mor är båda hästar i denna tabell
    om vi har dem. Morfar fås via mother.father. Far och mor kan vara
    inhemska tävlingshästar eller utländska avelshästar som aldrig tävlat
    här - båda får rader, men avelshästar har inga `starts`.
    """

    __tablename__ = "horses"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    sex: Mapped[str | None] = mapped_column(String(20))  # mare, stallion, gelding, colt, filly
    color: Mapped[str | None] = mapped_column(String(30))
    birth_year: Mapped[int | None] = mapped_column(Integer, index=True)
    country_of_birth: Mapped[str | None] = mapped_column(String(5))  # ISO eller längre länderkoder

    father_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("horses.id"), index=True
    )
    mother_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("horses.id"), index=True
    )

    # Senast kända ägaruppgifter - uppdateras vid varje ingest
    last_known_owner: Mapped[str | None] = mapped_column(String(200))
    last_known_breeder: Mapped[str | None] = mapped_column(String(200))

    # Pengainformation lagras alltid i smallest unit (öre, cents, sen)
    # tillsammans med currency på meeting/race-nivån
    career_earnings_minor: Mapped[int | None] = mapped_column(BigInteger)

    notes: Mapped[str | None] = mapped_column(Text)

    father: Mapped["Horse | None"] = relationship(
        "Horse", remote_side="Horse.id", foreign_keys=[father_id], post_update=True
    )
    mother: Mapped["Horse | None"] = relationship(
        "Horse", remote_side="Horse.id", foreign_keys=[mother_id], post_update=True
    )


class Person(Base, UUIDPrimaryKey, TimestampMixin):
    """Universell person - kusk, jockey, tränare, ägare, uppfödare.

    Samma person kan ha flera roller i flera länder. Roll definieras inte
    här utan implicit via vilken FK från andra tabeller som pekar hit
    (race.rider_id = ridroll, race.trainer_id = tränarroll).

    Vi sparar `country_code` som hemland men det är vägledning, inte tvång -
    många toppkuskar/jockeys är internationellt aktiva.
    """

    __tablename__ = "persons"

    # Vissa källor levererar bara fullständigt namn, andra första/efternamn separat
    # Vi sparar både för flexibilitet
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    short_name: Mapped[str | None] = mapped_column(String(30))  # "Per Linderoth" → "Lin Pe"

    birth_year: Mapped[int | None] = mapped_column(Integer)
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"))
    location: Mapped[str | None] = mapped_column(String(200))

    # License-info - kan vara t.ex. "A-tränare" på svenska eller "jockey" på engelska
    license_type: Mapped[str | None] = mapped_column(String(100))


class ExternalId(Base, TimestampMixin):
    """Mappar (datakälla, deras_id, entitetstyp) → vår interna UUID.

    Detta är limmet som gör att samma häst i ATG (ID 782100) och PMU
    (ID 567890) blir samma rad i `horses` med samma interna UUID.

    Vid ingest: kolla först om en extern ID finns, isåfall slå upp den
    interna entiteten. Annars försök matcha via namn+födelseår etc, eller
    skapa ny.
    """

    __tablename__ = "external_ids"
    __table_args__ = (
        UniqueConstraint(
            "source_code", "entity_type", "external_id",
            name="uq_external_id_source_type_id",
        ),
        Index("ix_external_id_lookup", "source_code", "entity_type", "external_id"),
        Index("ix_external_id_reverse", "internal_id", "entity_type"),
    )

    # Sammansatt PK över alla tre fält
    source_code: Mapped[str] = mapped_column(
        ForeignKey("data_sources.code"), primary_key=True
    )
    entity_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    # 'horse', 'person', 'track', 'race', 'start', 'meeting'
    external_id: Mapped[str] = mapped_column(String(100), primary_key=True)

    internal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # När mappingen först skapades och senast sågs - användbart för debug
    first_seen_at: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen_at: Mapped[date] = mapped_column(Date, nullable=False)
