"""Seeda referensdata (countries, disciplines, data_sources).

Kör:
    uv run python scripts/seed_reference_data.py

Idempotent - kan köras om utan att duplicera. Använder ON CONFLICT DO NOTHING.
"""

from sqlalchemy.dialects.postgresql import insert as pg_insert

from travai.db import session_scope
from travai.db.models import Country, DataSource, Discipline
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


def seed() -> None:
    """Seeda referensdata med UPSERT-mönster."""
    with session_scope() as session:
        for table_class, rows in [
            (Country, COUNTRIES),
            (Discipline, DISCIPLINES),
            (DataSource, DATA_SOURCES),
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
