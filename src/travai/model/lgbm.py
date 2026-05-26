"""LightGBM LambdaRank-modell för hästkapplöpningsranking.

LambdaRank lär sig att ranka hästar inom samma lopp (race_id som group).
Target är `relevance_score` där vinnaren har högst score.

Output: en score per start. Inom samma lopp kan vi sortera hästarna efter
score. Vi konverterar också till sannolikheter via softmax.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from travai.logging_setup import get_logger
from travai.model.dataset import FeatureDataset

logger = get_logger(__name__)


# Default hyperparametrar - balanserade för 600k+ träningsrader
DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "ndcg_eval_at": [1, 3, 5],
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 5,
    "lambda_l1": 0.0,
    "lambda_l2": 1.0,
    "verbose": -1,
    "num_threads": 0,  # 0 = använd alla
    # LambdaRank-specifika
    "lambdarank_truncation_level": 12,  # truncate vid topp-12 (medel-race är ~10 hästar)
}


@dataclass
class LambdaRankModel:
    """En tränad LambdaRank-modell + metadata."""

    booster: lgb.Booster
    feature_names: list[str]
    categorical_features: list[str]
    params: dict[str, Any]
    best_iteration: int

    def predict(self, X: pd.DataFrame) -> np.ndarray:  # noqa: N803
        """Returnera raw scores."""
        return self.booster.predict(X, num_iteration=self.best_iteration)

    def predict_with_softmax(self, X: pd.DataFrame, group_sizes: np.ndarray) -> np.ndarray:  # noqa: N803
        """Returnera sannolikheter via softmax inom varje race.

        Detta ger P(häst vinner | lopp) som summerar till 1.0 per lopp.
        Inte perfekt kalibrerad, men en rimlig approximation av vinstchans.
        """
        scores = self.predict(X)
        probs = np.zeros_like(scores)
        offset = 0
        for size in group_sizes:
            chunk = scores[offset : offset + size]
            # Numerisk stabilitet
            chunk_shifted = chunk - chunk.max()
            exp_chunk = np.exp(chunk_shifted)
            probs[offset : offset + size] = exp_chunk / exp_chunk.sum()
            offset += size
        return probs

    def save(self, model_dir: Path) -> None:
        """Spara modell + metadata."""
        model_dir.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(str(model_dir / "model.lgb"))
        meta = {
            "feature_names": self.feature_names,
            "categorical_features": self.categorical_features,
            "params": self.params,
            "best_iteration": self.best_iteration,
        }
        with open(model_dir / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)
        logger.info("model_saved", dir=str(model_dir))

    @classmethod
    def load(cls, model_dir: Path) -> LambdaRankModel:
        booster = lgb.Booster(model_file=str(model_dir / "model.lgb"))
        with open(model_dir / "meta.json") as f:
            meta = json.load(f)
        return cls(
            booster=booster,
            feature_names=meta["feature_names"],
            categorical_features=meta["categorical_features"],
            params=meta["params"],
            best_iteration=meta["best_iteration"],
        )


def train_model(
    train: FeatureDataset,
    val: FeatureDataset,
    categorical_features: list[str] | None = None,
    params: dict[str, Any] | None = None,
    num_boost_round: int = 2000,
    early_stopping_rounds: int = 50,
) -> LambdaRankModel:
    """Träna en LambdaRank-modell med early stopping på val-set."""
    params = {**DEFAULT_PARAMS, **(params or {})}
    categorical_features = categorical_features or []

    logger.info(
        "train_start",
        train_rows=train.n_rows,
        train_races=train.n_races,
        val_rows=val.n_rows,
        val_races=val.n_races,
        features=len(train.feature_names),
        params=params,
    )

    train_dataset = lgb.Dataset(
        train.X,
        label=train.y,
        group=train.group,
        categorical_feature=categorical_features,
        feature_name=train.feature_names,
        free_raw_data=False,
    )
    val_dataset = lgb.Dataset(
        val.X,
        label=val.y,
        group=val.group,
        categorical_feature=categorical_features,
        reference=train_dataset,
        free_raw_data=False,
    )

    callbacks = [
        lgb.early_stopping(stopping_rounds=early_stopping_rounds, verbose=True),
        lgb.log_evaluation(period=50),
    ]

    booster = lgb.train(
        params,
        train_dataset,
        num_boost_round=num_boost_round,
        valid_sets=[train_dataset, val_dataset],
        valid_names=["train", "val"],
        callbacks=callbacks,
    )

    logger.info(
        "train_done",
        best_iteration=booster.best_iteration,
        best_score=dict(booster.best_score.get("val", {})),
    )

    return LambdaRankModel(
        booster=booster,
        feature_names=train.feature_names,
        categorical_features=categorical_features,
        params=params,
        best_iteration=booster.best_iteration,
    )


def feature_importance(model: LambdaRankModel, top_n: int = 20) -> pd.DataFrame:
    """Returnera top features sorted by importance (gain)."""
    importance = model.booster.feature_importance(importance_type="gain")
    df = pd.DataFrame({"feature": model.feature_names, "importance": importance}).sort_values(
        "importance", ascending=False
    )
    return df.head(top_n).reset_index(drop=True)
