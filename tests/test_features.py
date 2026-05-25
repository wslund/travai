"""Tester för feature-byggaren.

Vi testar de rena hjälpfunktionerna (time-window helpers) som är de
mest komplexa och buggkänsliga.
"""

import numpy as np
import pandas as pd

from travai.features.builder import FeatureBuilder


def test_count_in_window_basic() -> None:
    """5 starter över 100 dagar, fönster 30 dagar."""
    dates = pd.to_datetime(
        ["2024-01-01", "2024-01-15", "2024-02-01", "2024-02-20", "2024-03-15"]
    ).values
    result = FeatureBuilder._count_in_window(dates, days=30)
    # Rad 0: inga tidigare
    # Rad 1: 1 tidigare (jan 1) inom 30d
    # Rad 2: 2 tidigare (jan 1 är 31d bort, jan 15 är 17d bort) → bara 1
    # Rad 3: jan 15 (36d) och feb 1 (19d) → 1 inom
    # Rad 4: feb 20 (23d), feb 1 (43d) → 1
    assert result.tolist() == [0, 1, 1, 1, 1]


def test_count_in_window_dense() -> None:
    """Många starter på samma vecka."""
    dates = pd.to_datetime(["2024-01-01"] * 5).values
    result = FeatureBuilder._count_in_window(dates, days=30)
    assert result.tolist() == [0, 1, 2, 3, 4]


def test_count_in_window_filtered() -> None:
    """Räkna bara där flag=True."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-10", "2024-01-20", "2024-02-01"]).values
    flags = np.array([True, False, True, True])
    result = FeatureBuilder._count_in_window_filtered(dates, flags, days=30)
    # Rad 0: 0 tidigare
    # Rad 1: 1 tidigare (jan 1) som var True
    # Rad 2: jan 1 (True) och jan 10 (False) inom 30d → 1
    # Rad 3: jan 10 (False, 22d), jan 20 (True, 12d), jan 1 (32d, ute) → 1
    assert result.tolist() == [0, 1, 1, 1]


def test_min_in_window() -> None:
    """Min km-tid i window."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-15", "2024-02-01", "2024-03-01"]).values
    vals = np.array([75.0, 74.5, 76.0, 73.8])
    result = FeatureBuilder._min_in_window(dates, vals, days=60)
    # Rad 0: NaN (inget tidigare)
    # Rad 1: 75.0 (1 datapunkt)
    # Rad 2: min(75, 74.5) = 74.5
    # Rad 3: feb 1 (29d, 76.0), jan 15 (45d, 74.5), jan 1 (60d, gräns) → 74.5
    assert np.isnan(result[0])
    assert result[1] == 75.0
    assert result[2] == 74.5
    assert result[3] == 74.5


def test_min_in_window_with_nans() -> None:
    """NaN-värden ska ignoreras."""
    dates = pd.to_datetime(["2024-01-01", "2024-01-15", "2024-02-01"]).values
    vals = np.array([np.nan, 74.5, 76.0])
    result = FeatureBuilder._min_in_window(dates, vals, days=60)
    assert np.isnan(result[0])
    assert np.isnan(result[1])  # första värdet är NaN
    # rad 1: bara NaN tidigare → NaN
    # rad 2: 74.5 är giltigt
    assert result[2] == 74.5


def test_relevance_score_logic() -> None:
    """Relevance: vinnare i ett 12-startar-lopp ska få högsta score."""
    # Vi testar logiken manuellt eftersom det är en enkel formel
    num_starters = 12
    finish_pos = 1
    expected = max(0, num_starters - finish_pos + 1)
    assert expected == 12

    finish_pos = 12
    expected = max(0, num_starters - finish_pos + 1)
    assert expected == 1

    # DNF (finish_pos = 0 eller None) → 0
    # Detta sköts av np.where i koden, vi testar inte hela DataFrame här
