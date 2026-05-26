"""Tester för LightGBM-modellmodulen.

Testar de rena, deterministiska delarna utan att kräva databas eller
verkliga features. Integrationstester med riktig data körs manuellt via
scripts/train.py.
"""

import numpy as np
import pandas as pd

from travai.model.dataset import FeatureDataset
from travai.model.evaluation import _backtest_favorite, _backtest_top_pick, _ndcg


def test_ndcg_perfect_ranking() -> None:
    """Perfekt ranking → NDCG = 1.0."""
    # Vinnaren (relevance=3) listas först
    ranked_rel = np.array([3.0, 2.0, 1.0, 0.0])
    score = _ndcg(ranked_rel, k=3, y_true_full=ranked_rel)
    assert abs(score - 1.0) < 1e-6


def test_ndcg_worst_ranking() -> None:
    """Sämsta möjliga ranking → NDCG < 1.0."""
    # Vinnaren (relevance=3) listas sist
    ranked_rel = np.array([0.0, 1.0, 2.0, 3.0])
    score = _ndcg(ranked_rel, k=3, y_true_full=np.array([3.0, 2.0, 1.0, 0.0]))
    assert score < 0.5


def _make_dataset(n_races: int = 3, race_size: int = 5, winner_at_index: int = 0) -> FeatureDataset:
    """Skapa ett test-dataset där vinnaren har lägsta odds."""
    n = n_races * race_size
    X = pd.DataFrame({"f1": np.random.rand(n), "f2": np.random.rand(n)})  # noqa: N806

    positions = []
    odds = []
    for _ in range(n_races):
        race_positions = [99] * race_size
        race_positions[winner_at_index] = 1
        race_positions[(winner_at_index + 1) % race_size] = 2
        race_positions[(winner_at_index + 2) % race_size] = 3
        positions.extend(race_positions)

        # Vinnaren har lägsta odds
        race_odds = [10.0] * race_size
        race_odds[winner_at_index] = 2.0
        odds.extend(race_odds)

    relevance = [race_size - p + 1 if p <= race_size else 0 for p in positions]

    return FeatureDataset(
        X=X,
        y=np.array(relevance, dtype="int32"),
        group=np.array([race_size] * n_races, dtype="int32"),
        race_ids=np.array([f"r{i // race_size}" for i in range(n)]),
        horse_ids=np.array([f"h{i}" for i in range(n)]),
        start_ids=np.array([f"s{i}" for i in range(n)]),
        race_dates=pd.Series([pd.Timestamp("2025-01-01")] * n),
        finish_positions=np.array(positions, dtype="int64"),
        final_win_odds=np.array(odds, dtype="float64"),
    )


def test_backtest_favorite_always_wins() -> None:
    """Om vinnaren alltid är favoriten ska favorit-strategin ha 100% hit rate."""
    ds = _make_dataset(n_races=10, race_size=5, winner_at_index=0)
    # Skapa scores där favorit alltid är index 0
    result = _backtest_favorite("favorite", ds, stake=1.0)
    assert result.n_bets == 10
    assert result.n_wins == 10
    # ROI = (10 * 2.0 - 10) / 10 = 1.0 (100% vinst)
    assert abs(result.roi - 1.0) < 1e-6


def test_backtest_top_pick_perfect_model() -> None:
    """Om modellens scores är 'rätt' (lägst odds = högst score)
    ska vi vinna alla lopp."""
    ds = _make_dataset(n_races=10, race_size=5, winner_at_index=0)
    # Skapa scores: vinnaren har högst score
    scores = np.tile([10.0, 1.0, 1.0, 1.0, 1.0], 10)
    result = _backtest_top_pick("model_top_pick", scores, ds, stake=1.0)
    assert result.n_bets == 10
    assert result.n_wins == 10


def test_backtest_top_pick_bad_model() -> None:
    """Om modellen är dålig och alltid pickar fel häst ska vi förlora."""
    ds = _make_dataset(n_races=10, race_size=5, winner_at_index=0)
    # Modellen rankar position 4 högst (förloraren)
    scores = np.tile([1.0, 1.0, 1.0, 1.0, 10.0], 10)
    result = _backtest_top_pick("model_top_pick", scores, ds, stake=1.0)
    assert result.n_bets == 10
    assert result.n_wins == 0
    assert result.roi == -1.0  # förlorat allt
