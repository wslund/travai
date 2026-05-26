"""Träna en LightGBM LambdaRank-modell på TravAI-features.

Användning:
    uv run python scripts/train.py
    uv run python scripts/train.py --model-dir models/v1
    uv run python scripts/train.py --train-end 2024-01-01 --val-end 2025-01-01
"""

import argparse
from datetime import date
from pathlib import Path

from travai.logging_setup import configure_logging, get_logger
from travai.model.dataset import (
    DEFAULT_TRAIN_END,
    DEFAULT_VAL_END,
    load_dataset,
)
from travai.model.evaluation import evaluate, evaluate_betting_roi
from travai.model.lgbm import feature_importance, train_model

logger = get_logger(__name__)


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
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    logger.info("training_pipeline_start", model_dir=str(args.model_dir))

    # 1. Ladda och splitta data
    splits = load_dataset(train_end=args.train_end, val_end=args.val_end)

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
