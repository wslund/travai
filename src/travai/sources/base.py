"""Abstrakt adapter-bas. Varje datakälla (ATG, PMU, HKJC...) implementerar
detta interface för att integrera sin data i den globala modellen.

Designprincip: adaptern äger mappningen från datakällans format till vår
interna kanoniska modell. När en ny marknad ska stödjas är det här man
börjar - inte i schemat eller ingest-koden.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import date
from typing import Any

from sqlalchemy.orm import Session


class SourceAdapter(ABC):
    """Bas-klass för alla datakällsadaptrar."""

    #: Kort kod som matchar `data_sources.code` (t.ex. 'atg', 'pmu')
    source_code: str

    @abstractmethod
    async def list_meetings(self, day: date) -> list[dict[str, Any]]:
        """Hämta alla tävlingar (meetings) som körs en specifik dag.

        Returnerar en list av minimala dict:ar med åtminstone {'external_id', 'track'}.
        Detaljerad data hämtas via `fetch_meeting`.
        """

    @abstractmethod
    async def fetch_meeting(self, external_id: str) -> dict[str, Any]:
        """Hämta komplett rådata för en meeting från källan."""

    @abstractmethod
    def ingest_meeting(self, session: Session, raw_data: dict[str, Any]) -> dict[str, int]:
        """Persistera en meeting och alla nestade entiteter till databasen.

        Skall vara idempotent: att köra om samma data uppdaterar istället
        för duplicerar. Returnerar en räknare över bearbetade entiteter.

        Implementeras typiskt så här:
        1) Spara raw_data i raw_payloads-tabellen
        2) Mappa till tracks/meetings/races/horses/persons/starts
        3) Använd ExternalId för att hitta eller skapa interna entiteter
        4) UPSERT på alla rader
        """

    async def iter_dates_range(
        self,
        start: date,
        end: date,
    ) -> Iterator[date]:
        """Iterera över datum mellan start och end (inkl.). Hjälpare för backfill."""
        from datetime import timedelta

        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)
