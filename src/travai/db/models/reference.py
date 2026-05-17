"""Referensdata - relativt statiska lookup-tabeller.

Dessa har korta string-PKs (ISO-koder etc) istället för UUID eftersom de
används som FK i många andra tabeller och små stabila koder är trevligare
att felsöka mot än UUID:er.
"""

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from travai.db.base import Base, TimestampMixin


class Country(Base, TimestampMixin):
    """ISO 3166-1 alpha-2 landskod."""

    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)  # SE, FR, US, HK, JP, GB, IE, AU, NO
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))  # SEK, EUR, USD, HKD, JPY


class Discipline(Base, TimestampMixin):
    """Hästsportsdisciplin.

    En `code` används som FK från races så vi vet exakt vad som körs.
    `sport` grupperar discipliner i 'trot' och 'gallop' för UI/filter.
    """

    __tablename__ = "disciplines"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    # Värden vid initial seed:
    #  - trot_sulky        (vagn med sulky - Sverige, Norge, Frankrike Attelé, USA Standardbred)
    #  - trot_mounted      (monté-trav - kusk sitter på hästen - Frankrike Monté)
    #  - flat              (galopp över plant)
    #  - hurdle            (hopprace över häckar - lägre hinder)
    #  - steeplechase      (hopprace över stora hinder)
    #  - cross_country     (cross över naturlig terräng)
    sport: Mapped[str] = mapped_column(String(20), nullable=False)  # 'trot' eller 'gallop'
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class DataSource(Base, TimestampMixin):
    """En källa vi hämtar data från.

    Värden vid initial seed:
    - atg          (Sverige - svensk trav)
    - pmu          (Frankrike - trav och galopp)
    - hkjc         (Hong Kong - galopp)
    - racing_api   (UK/IE/HK/AUS/USA via The Racing API)
    - equibase     (USA - galopp och standardbred)
    - jra          (Japan - galopp via netkeiba)
    - rikstoto     (Norge - trav)
    """

    __tablename__ = "data_sources"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"))
    base_url: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)


class BetType(Base, TimestampMixin):
    """En spelform i ett land hos en operatör.

    En spelform identifieras unikt av (operator, code), eftersom samma kod
    kan förekomma hos olika operatörer (t.ex. 'WIN' överallt). `legs` är
    antal lopp man behöver pricka in (V75 = 7, Pick 6 = 6, vinnare = 1).
    """

    __tablename__ = "bet_types"
    __table_args__ = (UniqueConstraint("operator", "code", name="uq_bet_type_operator_code"),)

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    operator: Mapped[str] = mapped_column(String(50), primary_key=True)  # 'atg', 'pmu', 'hkjc' etc
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    legs: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_jackpot: Mapped[bool] = mapped_column(default=False)
