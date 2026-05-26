"""Jämför två sparade modeller side-by-side på test-set.

Användning:
    uv run python scripts/compare_models.py \\
        --model-a models/latest \\
        --model-b models/pre_odds_close
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
    parser = argparse.ArgumentParser(description="Jämför två sparade modeller")
    parser.add_argument("--model-a", type=Path, required=True)
    parser.add_argument("--model-b", type=Path, required=True)
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
        "--split",
        choices=["train", "val", "test"],
        default="test",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    model_a = LambdaRankModel.load(args.model_a)
    model_b = LambdaRankModel.load(args.model_b)

    print(f"\nModell A: {args.model_a}")
    print(f"  Best iteration: {model_a.best_iteration}")
    print(f"  Antal features: {len(model_a.feature_names)}")

    print(f"\nModell B: {args.model_b}")
    print(f"  Best iteration: {model_b.best_iteration}")
    print(f"  Antal features: {len(model_b.feature_names)}")

    # Diff av feature-sets
    a_set = set(model_a.feature_names)
    b_set = set(model_b.feature_names)
    only_in_a = sorted(a_set - b_set)
    only_in_b = sorted(b_set - a_set)
    if only_in_a:
        print(f"\nFeatures bara i A: {', '.join(only_in_a)}")
    if only_in_b:
        print(f"Features bara i B: {', '.join(only_in_b)}")

    # Ladda data med modell A:s feature-set
    # (Vi måste ladda data två gånger för att respektera respektive
    # modells feature-set, eftersom de kan skilja sig)
    exclude_for_a = sorted(b_set - a_set)
    exclude_for_b = sorted(a_set - b_set)

    print(f"\nUtvärderar på split: {args.split}")
    print("=" * 70)

    for label, model, exclude in [
        (f"A ({args.model_a.name})", model_a, exclude_for_a),
        (f"B ({args.model_b.name})", model_b, exclude_for_b),
    ]:
        splits = load_dataset(
            train_end=args.train_end,
            val_end=args.val_end,
            exclude_features=exclude,
        )
        ds = {"train": splits.train, "val": splits.val, "test": splits.test}[args.split]

        print(f"\n--- Modell {label} ---")
        result = evaluate(model, ds)
        print(result.display())

        print("\nBetting backtest:")
        for br in evaluate_betting_roi(model, ds, stake=1.0):
            print(br.display())
            print()


if __name__ == "__main__":
    main()
