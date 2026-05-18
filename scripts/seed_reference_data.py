"""Seeda referensdata (countries, disciplines, data_sources, bet_types).

Kör:
    uv run python scripts/seed_reference_data.py

Idempotent - kan köras om utan att duplicera.
"""

from sqlalchemy.dialects.postgresql import insert as pg_insert

from travai.db import session_scope
from travai.db.models import BetType, Country, DataSource, Discipline
from travai.logging_setup import configure_logging, get_logger

logger = get_logger(__name__)


COUNTRIES = [
    {"code": "SE", "name": "Sverige", "currency_code": "SEK"},
    {"code": "FR", "name": "France", "currency_code": "EUR"},
    {"code": "GB", "name": "United Kingdom", "currency_code": "GBP"},
    {"code": "IE", "name": "Ireland", "currency_code": "EUR"},
    {"code": "US", "name": "United States", "currency_code": "USD"},
    {"code": "HK", "name": "Hong Kong", "currency_code": "HKD"},
    {"code": "JP", "name": "Japan", "currency_code": "JPY"},
    {"code": "AU", "name": "Australia", "currency_code": "AUD"},
    {"code": "NO", "name": "Norge", "currency_code": "NOK"},
    {"code": "DK", "name": "Danmark", "currency_code": "DKK"},
    {"code": "FI", "name": "Suomi", "currency_code": "EUR"},
    {"code": "DE", "name": "Deutschland", "currency_code": "EUR"},
    {"code": "IT", "name": "Italia", "currency_code": "EUR"},
]


DISCIPLINES = [
    {"code": "trot_sulky", "sport": "trot", "name": "Trav med sulky"},
    {"code": "trot_mounted", "sport": "trot", "name": "Monté-trav"},
    {"code": "flat", "sport": "gallop", "name": "Galopp på plant"},
    {"code": "hurdle", "sport": "gallop", "name": "Hopprace med häckar"},
    {"code": "steeplechase", "sport": "gallop", "name": "Steeplechase"},
    {"code": "cross_country", "sport": "gallop", "name": "Cross-country"},
]


DATA_SOURCES = [
    {
        "code": "atg",
        "name": "AB Trav och Galopp",
        "country_code": "SE",
        "base_url": "https://www.atg.se/services/racinginfo/v1/api",
        "notes": "Inofficiell JSON-API. Partneravtal behövs för produktion.",
    },
    {
        "code": "pmu",
        "name": "Pari Mutuel Urbain",
        "country_code": "FR",
        "base_url": "https://offline.turfinfo.api.pmu.fr/rest/client/7",
        "notes": "Inofficiell JSON. Hierarki: programme > reunions > courses > participants.",
    },
    {
        "code": "hkjc",
        "name": "Hong Kong Jockey Club",
        "country_code": "HK",
        "notes": "Data från 1979. GraphQL-API. Sectional times per 200m.",
    },
    {
        "code": "racing_api",
        "name": "The Racing API",
        "country_code": "GB",
        "base_url": "https://api.theracingapi.com",
        "notes": "Kommersiell tredjepart, kräver abonnemang. UK/IE/HK kärna + USA/AUS som tillägg.",
    },
    {
        "code": "equibase",
        "name": "Equibase",
        "country_code": "US",
        "notes": "Officiell US-databas. Stängd, ofta används tredjepart istället.",
    },
    {
        "code": "jra",
        "name": "Japan Racing Association (via netkeiba)",
        "country_code": "JP",
        "notes": "Stora marknaden, japansk text default.",
    },
    {
        "code": "rikstoto",
        "name": "Norsk Rikstoto",
        "country_code": "NO",
        "notes": "Norsk trav, liknar ATG.",
    },
]


# Bet types för svenska ATG. Pool-typer från ATG:s API.
BET_TYPES = [
    # Sammansatta spel (flera lopp)
    {
        "code": "V75",
        "operator": "atg",
        "country_code": "SE",
        "name": "V75",
        "legs": 7,
        "is_jackpot": True,
    },
    {
        "code": "V86",
        "operator": "atg",
        "country_code": "SE",
        "name": "V86",
        "legs": 8,
        "is_jackpot": True,
    },
    {
        "code": "V64",
        "operator": "atg",
        "country_code": "SE",
        "name": "V64",
        "legs": 6,
        "is_jackpot": False,
    },
    {
        "code": "V65",
        "operator": "atg",
        "country_code": "SE",
        "name": "V65",
        "legs": 6,
        "is_jackpot": False,
    },
    {
        "code": "GS75",
        "operator": "atg",
        "country_code": "SE",
        "name": "GS75",
        "legs": 7,
        "is_jackpot": True,
    },
    {
        "code": "V5",
        "operator": "atg",
        "country_code": "SE",
        "name": "V5",
        "legs": 5,
        "is_jackpot": False,
    },
    {
        "code": "V4",
        "operator": "atg",
        "country_code": "SE",
        "name": "V4",
        "legs": 4,
        "is_jackpot": False,
    },
    {
        "code": "V3",
        "operator": "atg",
        "country_code": "SE",
        "name": "V3",
        "legs": 3,
        "is_jackpot": False,
    },
    {
        "code": "DD",
        "operator": "atg",
        "country_code": "SE",
        "name": "Dagens Dubbel",
        "legs": 2,
        "is_jackpot": False,
    },
    {
        "code": "LD",
        "operator": "atg",
        "country_code": "SE",
        "name": "Lokal Dubbel",
        "legs": 2,
        "is_jackpot": False,
    },
    {
        "code": "TOP7",
        "operator": "atg",
        "country_code": "SE",
        "name": "Top 7",
        "legs": 7,
        "is_jackpot": False,
    },
    {
        "code": "RAKET",
        "operator": "atg",
        "country_code": "SE",
        "name": "Raket",
        "legs": 1,
        "is_jackpot": False,
    },
    # Enkla pari-mutuel-pooler (per lopp)
    {
        "code": "VINNARE",
        "operator": "atg",
        "country_code": "SE",
        "name": "Vinnare",
        "legs": 1,
        "is_jackpot": False,
    },
    {
        "code": "PLATS",
        "operator": "atg",
        "country_code": "SE",
        "name": "Plats",
        "legs": 1,
        "is_jackpot": False,
    },
    {
        "code": "VP",
        "operator": "atg",
        "country_code": "SE",
        "name": "Vinnare + Plats",
        "legs": 1,
        "is_jackpot": False,
    },
    {
        "code": "TVILLING",
        "operator": "atg",
        "country_code": "SE",
        "name": "Tvilling",
        "legs": 1,
        "is_jackpot": False,
    },
    {
        "code": "TRIO",
        "operator": "atg",
        "country_code": "SE",
        "name": "Trio",
        "legs": 1,
        "is_jackpot": False,
    },
    {
        "code": "KOMB",
        "operator": "atg",
        "country_code": "SE",
        "name": "Komb",
        "legs": 1,
        "is_jackpot": False,
    },
]


def seed() -> None:
    """Seeda referensdata med UPSERT-mönster."""
    with session_scope() as session:
        for table_class, rows in [
            (Country, COUNTRIES),
            (Discipline, DISCIPLINES),
            (DataSource, DATA_SOURCES),
            (BetType, BET_TYPES),
        ]:
            for row in rows:
                stmt = pg_insert(table_class).values(**row).on_conflict_do_nothing()
                session.execute(stmt)
            logger.info("seeded", table=table_class.__tablename__, count=len(rows))


def main() -> None:
    configure_logging()
    seed()


if __name__ == "__main__":
    main()
