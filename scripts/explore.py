"""Utforskande script - hämta dagens kalender från ATG och visa innehållet.

Kör:
    uv run python scripts/explore.py

eller med ett specifikt datum:
    uv run python scripts/explore.py 2025-01-25
"""

import asyncio
import json
import sys
from datetime import date

from travai.atg import ATGClient
from travai.logging_setup import configure_logging, get_logger

logger = get_logger(__name__)


async def explore(target_day: date) -> None:
    async with ATGClient() as client:
        logger.info("fetching_calendar", day=target_day.isoformat())
        calendar = await client.calendar_day(target_day)

        print(f"\n=== Kalender för {target_day.isoformat()} ===\n")

        # Visa vilka spel som körs den här dagen
        if not calendar.games:
            print("Inga spel hittade.")
            return

        print(f"Produkter denna dag: {list(calendar.games.keys())}\n")

        for product, games in calendar.games.items():
            print(f"  {product}: {len(games)} spel")
            for game in games[:3]:  # max 3 per produkt
                print(f"    - {game.id} (status: {game.status})")

        # Plocka första spelet vi hittar och titta närmare
        first_product = next(iter(calendar.games.keys()))
        first_game_id = calendar.games[first_product][0].id

        print(f"\n=== Detaljer för {first_game_id} ===\n")
        game = await client.game(first_game_id)

        print(f"Spel: {game.id}")
        print(f"Typ: {game.type}")
        print(f"Status: {game.status}")
        print(f"Antal lopp: {len(game.races)}")

        for race in game.races:
            print(
                f"  Lopp {race.number}: {race.name or '?'} "
                f"({race.distance}m, {race.startMethod}) - "
                f"{len(race.starts)} starter"
            )

        # Spara rådata till fil för utforskning
        raw = await client.game_raw(first_game_id)
        out_path = f"data/raw_{first_game_id}.json"

        import os

        os.makedirs("data", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)

        print(f"\nRådata sparad till: {out_path}")
        print("Öppna den i editorn för att se exakt vilka fält ATG returnerar.")


def main() -> None:
    configure_logging()

    target_day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()

    asyncio.run(explore(target_day))


if __name__ == "__main__":
    main()
