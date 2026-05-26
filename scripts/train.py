"""Träna en LightGBM LambdaRank-modell på TravAI-features.

Användning:
    # Träna med ALLA features (inklusive odds)
    uv run python scripts/train.py

    # Träna utan odds-features (live-scenario, pre odds-close)
    uv run python scripts/train.py --preset pre-odds-close \\
        --model-dir models/pre_odds_close

    # Egen exkluderingslista
    uv run python scripts/train.py --exclude-features final_win_odds,is_favorite
"""

import argparse
from datetime import date
from pathlib import Path

from travai.logging_setup import configure_logging, get_logger
from travai.model.dataset import (
    DEFAULT_TRAIN_END,
    DEFAULT_VAL_END,
    ODDS_FEATURES,
    load_dataset,
)
from travai.model.evaluation import evaluate, evaluate_betting_roi
from travai.model.lgbm import feature_importance, train_model

logger = get_logger(__name__)


PRESETS = {
    "all-features": [],  # Inget exkluderat — använd allt
    "pre-odds-close": ODDS_FEATURES,  # Simulera spel innan odds stänger
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Träna LambdaRank-modell")
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("models/latest"),
        help="Var modellen sparas",
    )
    parser.add_argument(
        "--train-end",
        type=date.fromisoformat,
        default=DEFAULT_TRAIN_END,
        help="Datum då train slutar (YYYY-MM-DD). Default 2024-01-01",
    )
    parser.add_argument(
        "--val-end",
        type=date.fromisoformat,
        default=DEFAULT_VAL_END,
        help="Datum då val slutar (YYYY-MM-DD). Default 2025-01-01",
    )
    parser.add_argument(
        "--num-rounds",
        type=int,
        default=2000,
        help="Max antal träningsrundor (early stopping kan stoppa tidigare)",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=None,
        help="Override learning rate (default 0.05)",
    )
    parser.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        default="all-features",
        help="Färdiga konfigurationer: all-features eller pre-odds-close",
    )
    parser.add_argument(
        "--exclude-features",
        type=str,
        default=None,
        help="Kommaseparerad lista av features att exkludera "
        "(utöver preset). T.ex. 'final_win_odds,is_favorite'",
    )
    return parser.parse_args()


def resolve_exclude_features(args: argparse.Namespace) -> list[str]:
    """Bygg ihop exclusion-listan från preset + explicit CLI."""
    excluded = list(PRESETS[args.preset])
    if args.exclude_features:
        extra = [f.strip() for f in args.exclude_features.split(",") if f.strip()]
        excluded.extend(extra)
    return sorted(set(excluded))


def main() -> None:
    configure_logging()
    args = parse_args()

    excluded = resolve_exclude_features(args)
    logger.info(
        "training_pipeline_start",
        model_dir=str(args.model_dir),
        preset=args.preset,
        excluded_features=excluded,
    )

    # 1. Ladda och splitta data
    splits = load_dataset(
        train_end=args.train_end,
        val_end=args.val_end,
        exclude_features=excluded,
    )

    print(f"\nFeatures som används ({len(splits.feature_names)}):")
    print(", ".join(splits.feature_names))
    if excluded:
        print(f"\nFeatures som exkluderats ({len(excluded)}):")
        print(", ".join(excluded))
    print()

    # 2. Träna
    params = {}
    if args.learning_rate is not None:
        params["learning_rate"] = args.learning_rate

    model = train_model(
        splits.train,
        splits.val,
        categorical_features=splits.categorical_features,
        params=params,
        num_boost_round=args.num_rounds,
    )

    # 3. Utvärdera på alla splits
    for name, ds in [
        ("train", splits.train),
        ("val", splits.val),
        ("test", splits.test),
    ]:
        result = evaluate(model, ds)
        print(f"\n=== {name.upper()} ===")
        print(result.display())

    # 4. Backtesta betting-strategier på test-set
    print("\n=== BETTING BACKTEST (TEST SET) ===")
    betting_results = evaluate_betting_roi(model, splits.test, stake=1.0, value_bet_threshold=0.0)
    for br in betting_results:
        print(br.display())
        print()

    # 5. Feature importance
    print("\n=== TOP 20 FEATURES BY IMPORTANCE ===")
    fi = feature_importance(model, top_n=20)
    print(fi.to_string(index=False))

    # 6. Spara modell
    model.save(args.model_dir)
    print(f"\nModell sparad i: {args.model_dir}")


if __name__ == "__main__":
    main()
