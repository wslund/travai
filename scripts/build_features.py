"""Bygg features-tabellen från transaktionsdata.

Kör:
    uv run python scripts/build_features.py

Eller med begränsning för test:
    uv run python scripts/build_features.py --limit 10000
"""

import argparse
import time

from travai.features import FeatureBuilder
from travai.logging_setup import configure_logging, get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bygg feature-tabellen")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximalt antal starts att processa (för utveckling/test)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Bygg DataFrame men skriv inte till databasen",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    start = time.time()

    builder = FeatureBuilder()
    df = builder.build_all(limit=args.limit)

    logger.info(
        "build_summary",
        rows=len(df),
        cols=len(df.columns),
        elapsed_sec=round(time.time() - start, 1),
    )

    # Visa lite stats
    logger.info(
        "feature_stats",
        unique_horses=df["horse_id"].nunique() if "horse_id" in df.columns else 0,
        unique_races=df["race_id"].nunique() if "race_id" in df.columns else 0,
        date_range=f"{df['race_date'].min()} → {df['race_date'].max()}"
        if "race_date" in df.columns
        else "n/a",
    )

    if args.dry_run:
        logger.info("dry_run_skipping_write")
        return

    write_start = time.time()
    builder.write(df)
    logger.info("write_elapsed_sec", elapsed=round(time.time() - write_start, 1))
    logger.info("done", total_elapsed_sec=round(time.time() - start, 1))


if __name__ == "__main__":
    main()
