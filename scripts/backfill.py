"""Historisk backfill av ATG-data.

Återupptagbar: kollar mot raw_payloads för att hoppa över games vi redan har.
Robust: enskilda fel stoppar inte hela jobbet.
Konfigurerbar: --from, --to, --products, --force, --dry-run.

Exempel:

    # Backfilla 2024 med default products (storspel + vardagsspel + dubbel)
    uv run python scripts/backfill.py --from 2024-01-01 --to 2024-12-31

    # Full täckning inkl. enskilda vinnare-pooler
    uv run python scripts/backfill.py --from 2024-01-01 --to 2024-12-31 \\
        --products "V75,V86,V64,V65,GS75,V5,V4,V3,dd,ld,top7,raket,vinnare"

    # Tvinga om-hämtning även om vi redan har data
    uv run python scripts/backfill.py --from 2024-01-01 --to 2024-01-07 --force

    # Visa vad som skulle göras utan att faktiskt köra
    uv run python scripts/backfill.py --from 2024-01-01 --to 2024-01-07 --dry-run
"""

import argparse
import asyncio
import sys
import time
from datetime import date, timedelta

from sqlalchemy import func, select

from travai.db import session_scope
from travai.db.models import RawPayload
from travai.logging_setup import configure_logging, get_logger
from travai.sources.atg import AtgAdapter

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill historisk ATG-data")
    parser.add_argument(
        "--from",
        dest="from_date",
        required=True,
        help="Startdatum (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=date.today().isoformat(),
        help="Slutdatum (YYYY-MM-DD), default idag",
    )
    parser.add_argument(
        "--products",
        help="Kommaseparerad lista över speltyper. Default: storspel + vardagsspel + dubbel",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-hämta även games vi redan har i raw_payloads",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista vad som skulle göras utan att faktiskt köra",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Börja från slutdatumet och gå bakåt (bra för att se nya data först)",
    )
    return parser.parse_args()


def has_raw_payload(external_id: str) -> bool:
    """Snabb-koll om vi redan har detta game i raw_payloads."""
    with session_scope() as session:
        count = session.execute(
            select(func.count(RawPayload.id)).where(
                RawPayload.source_code == "atg",
                RawPayload.entity_type == "game",
                RawPayload.external_id == external_id,
            )
        ).scalar()
        return count > 0


def date_range(start: date, end: date, reverse: bool = False) -> list[date]:
    """Generera alla datum mellan start och end (inkl)."""
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    if reverse:
        days.reverse()
    return days


async def backfill(args: argparse.Namespace) -> None:
    start_day = date.fromisoformat(args.from_date)
    end_day = date.fromisoformat(args.to_date)

    products = (
        frozenset(p.strip() for p in args.products.split(","))
        if args.products
        else None  # låt AtgAdapter använda DEFAULT_PRODUCTS
    )

    days = date_range(start_day, end_day, reverse=args.reverse)
    total_days = len(days)

    logger.info(
        "backfill_start",
        from_date=start_day.isoformat(),
        to_date=end_day.isoformat(),
        total_days=total_days,
        products=sorted(products) if products else "default",
        dry_run=args.dry_run,
        force=args.force,
    )

    stats = {
        "days_processed": 0,
        "games_found": 0,
        "games_skipped_existing": 0,
        "games_ingested": 0,
        "games_failed": 0,
    }
    started_at = time.time()

    async with AtgAdapter(products=products) as adapter:
        for i, day in enumerate(days, 1):
            try:
                meetings = await adapter.list_meetings(day)
            except Exception as exc:
                logger.error("list_meetings_failed", day=day.isoformat(), error=str(exc))
                continue

            stats["games_found"] += len(meetings)

            if args.dry_run:
                logger.info("dry_run_day", day=day.isoformat(), meetings=len(meetings))
                stats["days_processed"] += 1
                continue

            for meeting in meetings:
                external_id = meeting["external_id"]

                if not args.force and has_raw_payload(external_id):
                    stats["games_skipped_existing"] += 1
                    continue

                try:
                    raw = await adapter.fetch_meeting(external_id)
                    with session_scope() as session:
                        adapter.ingest_meeting(session, raw)
                    stats["games_ingested"] += 1
                except Exception as exc:
                    logger.error(
                        "ingest_failed",
                        external_id=external_id,
                        error=str(exc),
                    )
                    stats["games_failed"] += 1

            stats["days_processed"] += 1

            # Heartbeat var 10:e dag för progress
            if i % 10 == 0 or i == total_days:
                elapsed = time.time() - started_at
                rate = stats["days_processed"] / max(elapsed, 1)
                remaining = (total_days - i) / max(rate, 0.001)
                logger.info(
                    "backfill_progress",
                    progress=f"{i}/{total_days}",
                    elapsed_min=round(elapsed / 60, 1),
                    eta_min=round(remaining / 60, 1),
                    **stats,
                )

    elapsed = time.time() - started_at
    logger.info(
        "backfill_done",
        elapsed_min=round(elapsed / 60, 1),
        **stats,
    )


def main() -> None:
    configure_logging()
    args = parse_args()
    try:
        asyncio.run(backfill(args))
    except KeyboardInterrupt:
        logger.warning("backfill_interrupted_by_user")
        sys.exit(130)


if __name__ == "__main__":
    main()
