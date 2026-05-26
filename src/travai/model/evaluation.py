"""Utvärderingsmått för ranking-modeller och betting-ROI.

Två kategorier av mätvärden:

1. **Ranking-mått:** hur bra rankar vi inom lopp?
   - NDCG@1, @3 (träffar vi rätt vinnare?)
   - Top-1 hit rate (vinnar-träffsäkerhet)
   - Top-3 hit rate

2. **Betting-mått:** skulle vi tjäna pengar?
   - ROI om vi spelar 1 kr på modellens top-pick varje lopp
   - ROI om vi bara spelar "value bets" (P_model > 1/odds)
   - Jämförelse mot baseline (spela favoriten)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from travai.logging_setup import get_logger
from travai.model.dataset import FeatureDataset
from travai.model.lgbm import LambdaRankModel

logger = get_logger(__name__)


@dataclass
class EvaluationResult:
    """Sammanslagna mätvärden för en modell på ett dataset."""

    n_races: int
    n_starts: int

    # Ranking-mått
    top1_hit_rate: float  # andel lopp där modellens topp-pick vann
    top3_hit_rate: float  # andel lopp där modellens topp-pick blev top 3
    ndcg_at_1: float
    ndcg_at_3: float
    ndcg_at_5: float

    # Jämförelse med marknad (favoritspelet)
    market_top1_hit_rate: float  # baseline: alltid spela favoriten

    def display(self) -> str:
        return (
            f"Races: {self.n_races:,}, Starts: {self.n_starts:,}\n"
            f"Top-1 hit rate (modell): {self.top1_hit_rate * 100:.2f}%\n"
            f"Top-1 hit rate (favorit): {self.market_top1_hit_rate * 100:.2f}%\n"
            f"Top-3 hit rate (modell): {self.top3_hit_rate * 100:.2f}%\n"
            f"NDCG@1: {self.ndcg_at_1:.4f}\n"
            f"NDCG@3: {self.ndcg_at_3:.4f}\n"
            f"NDCG@5: {self.ndcg_at_5:.4f}"
        )


@dataclass
class BettingResult:
    """ROI-resultat för olika spelstrategier."""

    strategy: str
    n_bets: int
    n_wins: int
    total_stake: float
    total_return: float

    @property
    def hit_rate(self) -> float:
        return self.n_wins / self.n_bets if self.n_bets else 0.0

    @property
    def roi(self) -> float:
        return (
            (self.total_return - self.total_stake) / self.total_stake if self.total_stake else 0.0
        )

    @property
    def profit(self) -> float:
        return self.total_return - self.total_stake

    def display(self) -> str:
        return (
            f"Strategi: {self.strategy}\n"
            f"  Antal spel: {self.n_bets:,}\n"
            f"  Vinster: {self.n_wins:,} ({self.hit_rate * 100:.1f}%)\n"
            f"  Insatt: {self.total_stake:,.0f} kr\n"
            f"  Returer: {self.total_return:,.0f} kr\n"
            f"  Vinst: {self.profit:,.0f} kr\n"
            f"  ROI: {self.roi * 100:+.2f}%"
        )


def evaluate(model: LambdaRankModel, dataset: FeatureDataset) -> EvaluationResult:
    """Räkna ranking-mätvärden för en modell på ett dataset."""
    scores = model.predict(dataset.X)
    return _evaluate_from_scores(scores, dataset)


def _evaluate_from_scores(scores: np.ndarray, dataset: FeatureDataset) -> EvaluationResult:
    """Räkna ranking-mätvärden givet rådata och scores."""
    top1_hits = 0
    top3_hits = 0
    ndcg_at = {1: [], 3: [], 5: []}
    market_top1_hits = 0

    offset = 0
    n_races = 0

    # För market baseline behöver vi odds_rank (1 = favorit)
    # Eftersom dataset inte exponerar odds_rank direkt, vi använder
    # final_win_odds och letar minsta odds per lopp.

    for size in dataset.group:
        race_slice = slice(offset, offset + size)
        race_scores = scores[race_slice]
        race_positions = dataset.finish_positions[race_slice]
        race_odds = dataset.final_win_odds[race_slice]

        # Modellens topp-pick
        top_idx = np.argmax(race_scores)
        top_pos = race_positions[top_idx]
        if pd.notna(top_pos) and top_pos == 1:
            top1_hits += 1
        if pd.notna(top_pos) and top_pos <= 3:
            top3_hits += 1

        # Market baseline: lägsta odds (= favorit)
        valid_odds_mask = ~np.isnan(race_odds) & (race_odds > 0)
        if valid_odds_mask.any():
            valid_odds = np.where(valid_odds_mask, race_odds, np.inf)
            fav_idx = np.argmin(valid_odds)
            fav_pos = race_positions[fav_idx]
            if pd.notna(fav_pos) and fav_pos == 1:
                market_top1_hits += 1

        # NDCG@k
        order = np.argsort(-race_scores)
        relevance = (
            (race_positions > 0) & (~pd.isna(race_positions)) & (race_positions <= 12)
        ).astype(float)
        # Relevance: vinnare = max, etc
        # vi använder dataset.y direkt skulle vara renare men det är
        # samma info
        race_y = relevance
        for k in [1, 3, 5]:
            ndcg_at[k].append(_ndcg(race_y[order], k=k, y_true_full=race_y))

        offset += size
        n_races += 1

    return EvaluationResult(
        n_races=n_races,
        n_starts=int(dataset.n_rows),
        top1_hit_rate=top1_hits / n_races if n_races else 0.0,
        top3_hit_rate=top3_hits / n_races if n_races else 0.0,
        ndcg_at_1=float(np.mean(ndcg_at[1])),
        ndcg_at_3=float(np.mean(ndcg_at[3])),
        ndcg_at_5=float(np.mean(ndcg_at[5])),
        market_top1_hit_rate=market_top1_hits / n_races if n_races else 0.0,
    )


def _ndcg(ranked_relevance: np.ndarray, k: int, y_true_full: np.ndarray) -> float:
    """Standard NDCG@k."""
    k = min(k, len(ranked_relevance))
    rel = ranked_relevance[:k]
    discount = 1.0 / np.log2(np.arange(2, len(rel) + 2))
    dcg = float(np.sum((2**rel - 1) * discount))

    ideal = np.sort(y_true_full)[::-1][:k]
    idiscount = 1.0 / np.log2(np.arange(2, len(ideal) + 2))
    idcg = float(np.sum((2**ideal - 1) * idiscount))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_betting_roi(
    model: LambdaRankModel,
    dataset: FeatureDataset,
    stake: float = 1.0,
    value_bet_threshold: float = 0.0,
) -> list[BettingResult]:
    """Simulera olika spelstrategier.

    Strategier:
    1. "model_top_pick" - alltid spela modellens topp-pick (1 kr per lopp)
    2. "favorite" - alltid spela favoriten (baseline)
    3. "value_bets" - spela bara när P_model > 1/odds + threshold

    value_bet_threshold: edge-krav. 0.05 = "modellen ska tro 5%-enheter mer
                        än marknaden för att vi ska spela".
    """
    scores = model.predict(dataset.X)
    probs = model.predict_with_softmax(dataset.X, dataset.group)

    results: list[BettingResult] = []
    results.append(_backtest_top_pick("model_top_pick", scores, dataset, stake))
    results.append(_backtest_favorite("favorite", dataset, stake))
    results.append(
        _backtest_value_bets(
            "value_bets",
            probs,
            dataset,
            stake,
            edge_threshold=value_bet_threshold,
        )
    )
    return results


def _backtest_top_pick(
    name: str, scores: np.ndarray, dataset: FeatureDataset, stake: float
) -> BettingResult:
    n_bets = 0
    n_wins = 0
    total_stake = 0.0
    total_return = 0.0

    offset = 0
    for size in dataset.group:
        race_slice = slice(offset, offset + size)
        race_scores = scores[race_slice]
        race_pos = dataset.finish_positions[race_slice]
        race_odds = dataset.final_win_odds[race_slice]

        top_idx = int(np.argmax(race_scores))
        pos = race_pos[top_idx]
        odds = race_odds[top_idx]

        if pd.notna(odds) and odds > 0:
            n_bets += 1
            total_stake += stake
            if pd.notna(pos) and pos == 1:
                n_wins += 1
                total_return += stake * float(odds)

        offset += size

    return BettingResult(
        strategy=name,
        n_bets=n_bets,
        n_wins=n_wins,
        total_stake=total_stake,
        total_return=total_return,
    )


def _backtest_favorite(name: str, dataset: FeatureDataset, stake: float) -> BettingResult:
    """Baseline: spela alltid hästen med lägsta odds."""
    n_bets = 0
    n_wins = 0
    total_stake = 0.0
    total_return = 0.0

    offset = 0
    for size in dataset.group:
        race_slice = slice(offset, offset + size)
        race_odds = dataset.final_win_odds[race_slice]
        race_pos = dataset.finish_positions[race_slice]

        valid_mask = ~np.isnan(race_odds) & (race_odds > 0)
        if not valid_mask.any():
            offset += size
            continue

        valid_odds = np.where(valid_mask, race_odds, np.inf)
        fav_idx = int(np.argmin(valid_odds))

        n_bets += 1
        total_stake += stake
        pos = race_pos[fav_idx]
        odds = race_odds[fav_idx]
        if pd.notna(pos) and pos == 1:
            n_wins += 1
            total_return += stake * float(odds)

        offset += size

    return BettingResult(
        strategy=name,
        n_bets=n_bets,
        n_wins=n_wins,
        total_stake=total_stake,
        total_return=total_return,
    )


def _backtest_value_bets(
    name: str,
    probs: np.ndarray,
    dataset: FeatureDataset,
    stake: float,
    edge_threshold: float,
) -> BettingResult:
    """Spela hästar där modellens P > 1/odds + threshold."""
    n_bets = 0
    n_wins = 0
    total_stake = 0.0
    total_return = 0.0

    for i in range(len(probs)):
        odds = dataset.final_win_odds[i]
        if pd.isna(odds) or odds <= 0:
            continue

        market_prob = 1.0 / float(odds)  # marknadens implicit prob (utan margin)
        model_prob = float(probs[i])

        if model_prob - market_prob >= edge_threshold:
            n_bets += 1
            total_stake += stake
            pos = dataset.finish_positions[i]
            if pd.notna(pos) and pos == 1:
                n_wins += 1
                total_return += stake * float(odds)

    return BettingResult(
        strategy=name,
        n_bets=n_bets,
        n_wins=n_wins,
        total_stake=total_stake,
        total_return=total_return,
    )
