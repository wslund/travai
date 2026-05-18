"""Enhetstester för AtgAdapter:s rena hjälpfunktioner.

Vi testar parsing-hjälparna isolerat. Integration test mot Postgres
finns separat och kräver att docker compose-databasen kör.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from travai.sources.atg.adapter import AtgAdapter

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "atg_v75_minimal.json"


@pytest.fixture
def raw_game() -> dict:
    """Ladda fixture med minimal V75-data."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_km_time_normal() -> None:
    """1:14.7 -> 74.7 sekunder per km."""
    result = AtgAdapter._parse_km_time({"minutes": 1, "seconds": 14, "tenths": 7})
    assert result == Decimal("74.7")


def test_parse_km_time_zero_tenths() -> None:
    """1:15.0 -> 75.0."""
    result = AtgAdapter._parse_km_time({"minutes": 1, "seconds": 15, "tenths": 0})
    assert result == Decimal("75.0")


def test_parse_km_time_none() -> None:
    assert AtgAdapter._parse_km_time(None) is None


def test_parse_date_iso() -> None:
    assert AtgAdapter._parse_date("2025-05-10") == date(2025, 5, 10)


def test_parse_date_none() -> None:
    assert AtgAdapter._parse_date(None) is None
    assert AtgAdapter._parse_date("garbage") is None


def test_parse_datetime_with_offset() -> None:
    result = AtgAdapter._parse_datetime("2025-05-10T16:25:21")
    assert isinstance(result, datetime)
    assert result.year == 2025
    assert result.tzinfo is not None  # Vi sätter UTC om saknas


def test_fixture_parses_as_json(raw_game: dict) -> None:
    """Sanity: fixturen är giltig och har rätt struktur."""
    assert raw_game["id"] == "V75_2025-05-10_27_5"
    assert raw_game["type"] == "V75"
    assert len(raw_game["races"]) == 1
    assert len(raw_game["races"][0]["starts"]) == 1


def test_pool_to_snapshot_kwargs_vinnare() -> None:
    """Vinneoddset levereras som heltal *100 (11203 = 112.03)."""
    adapter = AtgAdapter.__new__(AtgAdapter)
    result = adapter._pool_to_snapshot_kwargs("vinnare", {"odds": 11203})
    assert result is not None
    assert result["odds_decimal"] == Decimal("112.03")


def test_pool_to_snapshot_kwargs_plats() -> None:
    """Platsoddset kommer som min/maxOdds."""
    adapter = AtgAdapter.__new__(AtgAdapter)
    result = adapter._pool_to_snapshot_kwargs("plats", {"minOdds": 1436, "maxOdds": 1500})
    assert result is not None
    assert result["odds_decimal"] == Decimal("14.36")
    assert result["odds_decimal_max"] == Decimal("15.0")


def test_pool_to_snapshot_kwargs_v75_distribution() -> None:
    """V75 ger spelfördelning i promille (82 = 8.2%)."""
    adapter = AtgAdapter.__new__(AtgAdapter)
    result = adapter._pool_to_snapshot_kwargs("V75", {"betDistribution": 82})
    assert result is not None
    assert result["pool_share"] == Decimal("0.082")


def test_pool_to_snapshot_kwargs_unknown() -> None:
    adapter = AtgAdapter.__new__(AtgAdapter)
    assert adapter._pool_to_snapshot_kwargs("nonsense", {"foo": "bar"}) is None
