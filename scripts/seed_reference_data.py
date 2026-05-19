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
    # Norden
    {"code": "SE", "name": "Sverige", "currency_code": "SEK"},
    {"code": "NO", "name": "Norge", "currency_code": "NOK"},
    {"code": "DK", "name": "Danmark", "currency_code": "DKK"},
    {"code": "FI", "name": "Suomi", "currency_code": "EUR"},
    {"code": "IS", "name": "Ísland", "currency_code": "ISK"},
    # Stora EU-länder
    {"code": "FR", "name": "France", "currency_code": "EUR"},
    {"code": "DE", "name": "Deutschland", "currency_code": "EUR"},
    {"code": "IT", "name": "Italia", "currency_code": "EUR"},
    {"code": "ES", "name": "España", "currency_code": "EUR"},
    {"code": "NL", "name": "Nederland", "currency_code": "EUR"},
    {"code": "BE", "name": "België", "currency_code": "EUR"},
    {"code": "AT", "name": "Österreich", "currency_code": "EUR"},
    {"code": "CH", "name": "Schweiz", "currency_code": "CHF"},
    {"code": "PL", "name": "Polska", "currency_code": "PLN"},
    {"code": "CZ", "name": "Česko", "currency_code": "CZK"},
    {"code": "HU", "name": "Magyarország", "currency_code": "HUF"},
    {"code": "PT", "name": "Portugal", "currency_code": "EUR"},
    {"code": "GR", "name": "Ελλάδα", "currency_code": "EUR"},
    {"code": "RO", "name": "România", "currency_code": "RON"},
    {"code": "IE", "name": "Ireland", "currency_code": "EUR"},
    # Storbritannien
    {"code": "GB", "name": "United Kingdom", "currency_code": "GBP"},
    # Östeuropa / OSS
    {"code": "RU", "name": "Россия", "currency_code": "RUB"},
    {"code": "UA", "name": "Україна", "currency_code": "UAH"},
    # Nordamerika
    {"code": "US", "name": "United States", "currency_code": "USD"},
    {"code": "CA", "name": "Canada", "currency_code": "CAD"},
    {"code": "MX", "name": "México", "currency_code": "MXN"},
    # Sydamerika
    {"code": "AR", "name": "Argentina", "currency_code": "ARS"},
    {"code": "BR", "name": "Brasil", "currency_code": "BRL"},
    {"code": "CL", "name": "Chile", "currency_code": "CLP"},
    {"code": "PE", "name": "Perú", "currency_code": "PEN"},
    # Asien
    {"code": "JP", "name": "Japan", "currency_code": "JPY"},
    {"code": "HK", "name": "Hong Kong", "currency_code": "HKD"},
    {"code": "SG", "name": "Singapore", "currency_code": "SGD"},
    {"code": "KR", "name": "한국", "currency_code": "KRW"},
    {"code": "MO", "name": "Macao", "currency_code": "MOP"},
    {"code": "IN", "name": "India", "currency_code": "INR"},
    {"code": "AE", "name": "الإمارات", "currency_code": "AED"},
    {"code": "TR", "name": "Türkiye", "currency_code": "TRY"},
    # Oceanien
    {"code": "AU", "name": "Australia", "currency_code": "AUD"},
    {"code": "NZ", "name": "New Zealand", "currency_code": "NZD"},
    # Afrika
    {"code": "ZA", "name": "South Africa", "currency_code": "ZAR"},
    {"code": "MA", "name": "Morocco", "currency_code": "MAD"},
    # Specialfall för okända/odefinierade
    {"code": "ZZ", "name": "Unknown", "currency_code": None},
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
        "notes": "Kommersiell tredjepart. UK/IE/HK kärna + USA/AUS som tillägg.",
    },
    {
        "code": "equibase",
        "name": "Equibase",
        "country_code": "US",
        "notes": "Officiell US-databas. Stängd, tredjepart används ofta.",
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


BET_TYPES = [
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
