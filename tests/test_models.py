"""Sanity-tester för att modellerna importeras och Base.metadata är komplett."""

from travai.db import Base
from travai.db.models import (
    Horse,
)


def test_all_expected_tables_in_metadata() -> None:
    """Alla huvudtabeller ska vara registrerade på Base.metadata."""
    expected = {
        "countries",
        "disciplines",
        "data_sources",
        "bet_types",
        "tracks",
        "horses",
        "persons",
        "external_ids",
        "meetings",
        "races",
        "starts",
        "sectional_times",
        "odds_snapshots",
        "equipment_changes",
        "weather_observations",
        "raw_payloads",
    }
    actual = {t.name for t in Base.metadata.tables.values()}
    missing = expected - actual
    assert not missing, f"Saknade tabeller: {missing}"


def test_features_schema_tables_exist() -> None:
    """Features-schema-tabellerna ska vara i metadata med rätt schema."""
    feature_tables = [t for t in Base.metadata.tables.values() if t.schema == "features"]
    expected_names = {
        "horse_form_snapshots",
        "track_post_position_stats",
        "person_rolling_stats",
    }
    actual_names = {t.name for t in feature_tables}
    assert actual_names == expected_names, (
        f"Förväntade feature-tabeller: {expected_names}, fick: {actual_names}"
    )


def test_horse_self_reference() -> None:
    """Hästens pedigree-FK ska peka till horses själv."""
    horse_cols = Horse.__table__.columns
    father_fk = next(iter(horse_cols["father_id"].foreign_keys))
    mother_fk = next(iter(horse_cols["mother_id"].foreign_keys))
    assert father_fk.column.table.name == "horses"
    assert mother_fk.column.table.name == "horses"
