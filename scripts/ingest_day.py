"""Hämta och spara alla intressanta ATG-spel för en dag.

Kör:
    uv run python scripts/ingest_day.py 2025-05-10

Eller utan argument för dagens datum:
    uv run python scripts/ingest_day.py
"""

import asyncio
import sys
from datetime import date

from travai.db import session_scope
from travai.logging_setup import configure_logging, get_logger
from travai.sources.atg import AtgAdapter

logger = get_logger(__name__)


async def ingest_day(target_day: date) -> None:
    async with AtgAdapter() as adapter:
        meetings = await adapter.list_meetings(target_day)

        if not meetings:
            logger.info("no_interesting_games", day=target_day.isoformat())
            return

        logger.info("ingesting_games", day=target_day.isoformat(), count=len(meetings))

        for meeting in meetings:
            external_id = meeting["external_id"]
            try:
                raw = await adapter.fetch_meeting(external_id)
                with session_scope() as session:
                    counts = adapter.ingest_meeting(session, raw)
                logger.info("game_ingested", external_id=external_id, **counts)
            except Exception as exc:
                logger.error("ingest_failed", external_id=external_id, error=str(exc))


def main() -> None:
    configure_logging()
    target_day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    asyncio.run(ingest_day(target_day))


if __name__ == "__main__":
    main()
