"""Utvärdera en sparad modell på test-data.

Användning:
    uv run python scripts/evaluate.py
    uv run python scripts/evaluate.py --model-dir models/v1 --value-threshold 0.05
"""

import argparse
from datetime import date
from pathlib import Path

from travai.logging_setup import configure_logging, get_logger
from travai.model.dataset import DEFAULT_TRAIN_END, DEFAULT_VAL_END, load_dataset
from travai.model.evaluation import evaluate, evaluate_betting_roi
from travai.model.lgbm import LambdaRankModel

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Utvärdera modell")
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("models/latest"),
        help="Var modellen finns",
    )
    parser.add_argument(
        "--train-end",
        type=date.fromisoformat,
        default=DEFAULT_TRAIN_END,
    )
    parser.add_argument(
        "--val-end",
        type=date.fromisoformat,
        default=DEFAULT_VAL_END,
    )
    parser.add_argument(
        "--value-threshold",
        type=float,
        default=0.0,
        help="Edge-krav för value bets (0.05 = modellen ska tro 5%%-enheter mer)",
    )
    parser.add_argument(
        "--split",
        choices=["train", "val", "test", "all"],
        default="test",
        help="Vilket split att utvärdera",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    model = LambdaRankModel.load(args.model_dir)
    print(f"Laddade modell från {args.model_dir}")
    print(f"Best iteration: {model.best_iteration}")

    splits = load_dataset(train_end=args.train_end, val_end=args.val_end)

    splits_dict = {
        "train": splits.train,
        "val": splits.val,
        "test": splits.test,
    }

    targets = [args.split] if args.split != "all" else ["train", "val", "test"]

    for name in targets:
        ds = splits_dict[name]
        print(f"\n=== {name.upper()} ===")
        result = evaluate(model, ds)
        print(result.display())

        print("\n--- Betting backtest ---")
        for br in evaluate_betting_roi(
            model, ds, stake=1.0, value_bet_threshold=args.value_threshold
        ):
            print(br.display())
            print()


if __name__ == "__main__":
    main()
