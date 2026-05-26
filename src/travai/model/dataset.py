"""Dataset-hantering för LightGBM-träning.

Läser features.start_features från databasen och splittar tidsmässigt.

OBS: tidsmässig split är KRITISK för sport-modellering. Random split skulle
leak information från framtiden (loppet före och efter är troligen med samma
häst, samma form, etc).

Splits:
- Train:    race_date < TRAIN_END (default 2024-01-01)
- Val:      TRAIN_END <= race_date < VAL_END (default 2025-01-01)
- Test:     race_date >= VAL_END

LambdaRank kräver att data är sorterad per group, samt en lista av
group_sizes (antal rader per group).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from travai.db import engine as default_engine
from travai.logging_setup import get_logger

logger = get_logger(__name__)


# Defaultsplits (kan överrideras)
DEFAULT_TRAIN_END = date(2024, 1, 1)
DEFAULT_VAL_END = date(2025, 1, 1)

# Identifierare och target-kolumner som INTE ska användas som features
NON_FEATURE_COLUMNS = {
    "start_id",
    "race_id",
    "horse_id",
    "race_date",
    "finish_position",
    "relevance_score",
    "created_at",
    "updated_at",
}

# Kolumner som ska behandlas som kategoriska av LightGBM
CATEGORICAL_COLUMNS = ["month", "day_of_week"]

# Odds-relaterade features. Användbara, men dessa kan vara delvis "läckage"
# från marknadens åsikt — om vi vill simulera pre-odds-close prediktion ska
# vi exkludera dem.
ODDS_FEATURES = [
    "final_win_odds",
    "log_final_win_odds",
    "odds_rank_in_race",
    "is_favorite",
    "v75_pool_share",
]


@dataclass
class FeatureDataset:
    """Ett dataset-split med X (features), y (relevance), group (race_sizes)."""

    X: pd.DataFrame
    y: np.ndarray
    group: np.ndarray  # antal rader per race_id, i ordning
    race_ids: np.ndarray  # race_id per rad (för utvärdering)
    horse_ids: np.ndarray
    start_ids: np.ndarray
    race_dates: pd.Series  # för att se vilken period vi är i
    finish_positions: np.ndarray  # raw finish (för backtest)
    final_win_odds: np.ndarray  # för ROI-backtest

    @property
    def n_rows(self) -> int:
        return len(self.X)

    @property
    def n_races(self) -> int:
        return len(self.group)

    @property
    def feature_names(self) -> list[str]:
        return list(self.X.columns)


@dataclass
class DatasetSplits:
    """Train/val/test-splits."""

    train: FeatureDataset
    val: FeatureDataset
    test: FeatureDataset
    feature_names: list[str]
    categorical_features: list[str]


def load_dataset(
    engine: Engine | None = None,
    train_end: date = DEFAULT_TRAIN_END,
    val_end: date = DEFAULT_VAL_END,
    min_starters: int = 3,
    exclude_features: list[str] | None = None,
) -> DatasetSplits:
    """Ladda features och splitta i train/val/test.

    Args:
        min_starters: minsta antal startande för att inkludera ett lopp.
                      Lopp med 1-2 hästar är inte meningsfulla att ranka.
        exclude_features: extra features att exkludera utöver
                          NON_FEATURE_COLUMNS. Användbart för "pre-odds-close"
                          modell-varianter.
    """
    engine = engine or default_engine
    exclude_features = exclude_features or []

    logger.info(
        "loading_features",
        train_end=str(train_end),
        val_end=str(val_end),
        exclude_features=exclude_features,
    )

    sql = """
    SELECT *
    FROM features.start_features
    WHERE finish_position IS NOT NULL
      AND num_starters >= :min_starters
    ORDER BY race_date, race_id, start_id
    """

    from sqlalchemy import text

    df = pd.read_sql(
        text(sql),
        engine,
        params={"min_starters": min_starters},
        parse_dates=["race_date"],
    )

    logger.info("features_loaded", rows=len(df), races=df["race_id"].nunique())

    train_mask = df["race_date"] < pd.Timestamp(train_end)
    val_mask = (df["race_date"] >= pd.Timestamp(train_end)) & (
        df["race_date"] < pd.Timestamp(val_end)
    )
    test_mask = df["race_date"] >= pd.Timestamp(val_end)

    train_df = df[train_mask].copy()
    val_df = df[val_mask].copy()
    test_df = df[test_mask].copy()

    logger.info(
        "splits",
        train_rows=len(train_df),
        train_races=train_df["race_id"].nunique(),
        val_rows=len(val_df),
        val_races=val_df["race_id"].nunique(),
        test_rows=len(test_df),
        test_races=test_df["race_id"].nunique(),
    )

    # Vilka kolumner är features?
    all_cols = set(df.columns)
    excluded = NON_FEATURE_COLUMNS | set(exclude_features)
    feature_cols = sorted(all_cols - excluded)

    logger.info(
        "feature_selection",
        total=len(feature_cols),
        excluded_extra=exclude_features,
    )

    return DatasetSplits(
        train=_build_dataset(train_df, feature_cols),
        val=_build_dataset(val_df, feature_cols),
        test=_build_dataset(test_df, feature_cols),
        feature_names=feature_cols,
        categorical_features=[c for c in CATEGORICAL_COLUMNS if c in feature_cols],
    )


def _build_dataset(df: pd.DataFrame, feature_cols: list[str]) -> FeatureDataset:
    """Bygg en FeatureDataset från en sorterad DataFrame.

    Data ska vara sorterad efter race_id för att group_sizes ska funka.
    """
    df = df.sort_values(["race_id", "start_id"]).reset_index(drop=True)

    # Group sizes: antal rader per race_id, i ordning
    group_sizes = df.groupby("race_id", sort=False).size().values

    X = df[feature_cols].copy()  # noqa: N806

    # Konvertera bool till int (LightGBM gillar inte bool)
    bool_cols = X.select_dtypes(include=["bool", "boolean"]).columns
    for col in bool_cols:
        X[col] = X[col].astype("Int64")

    # Konvertera Decimal/object till float där relevant
    for col in X.columns:
        if X[col].dtype == "object":
            X[col] = pd.to_numeric(X[col], errors="coerce")

    return FeatureDataset(
        X=X,
        y=df["relevance_score"].values.astype("int32"),
        group=group_sizes.astype("int32"),
        race_ids=df["race_id"].values,
        horse_ids=df["horse_id"].values,
        start_ids=df["start_id"].values,
        race_dates=df["race_date"],
        finish_positions=df["finish_position"].to_numpy(),
        final_win_odds=df["final_win_odds"].values.astype("float64")
        if "final_win_odds" in df.columns
        else np.zeros(len(df)),
    )
