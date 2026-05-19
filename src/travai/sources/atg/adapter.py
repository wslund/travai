"""ATG-adapter: mappar ATG:s rådata till det globala schemat.

Designprinciper:
- ExternalId-tabellen är limmet mellan ATG:s ID-rymd och våra interna UUID:er
- Operationer är idempotenta: kör om samma dag och samma rader uppdateras,
  inga dubletter skapas
- Hela ATG-svaret sparas alltid i raw_payloads så vi kan plocka fält senare
- Vid uppdatering rörs bara de fält där vi har ny information
- Defensiv felhantering: saknade fält ger tydliga meddelanden, okända länder
  faller tillbaka till ZZ istället för att krascha
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from travai.db.models import (
    Country,
    EquipmentChange,
    ExternalId,
    Horse,
    Meeting,
    OddsSnapshot,
    Person,
    Race,
    RawPayload,
    Start,
    Track,
)
from travai.logging_setup import get_logger
from travai.sources.atg.client import ATGClient
from travai.sources.base import SourceAdapter

logger = get_logger(__name__)

SOURCE_CODE = "atg"
FALLBACK_COUNTRY = "ZZ"  # Måste finnas i countries-tabellen via seed

START_METHOD_MAP = {
    "auto": "auto",
    "volte": "volte",
}


class AtgAdapter(SourceAdapter):
    """Adapter för svensk trav via ATG."""

    source_code = SOURCE_CODE

    DEFAULT_PRODUCTS: frozenset[str] = frozenset(
        {
            "V75",
            "V86",
            "V64",
            "V65",
            "GS75",
            "V5",
            "V4",
            "V3",
            "dd",
            "ld",
            "top7",
            "raket",
        }
    )

    FULL_COVERAGE_PRODUCTS: frozenset[str] = DEFAULT_PRODUCTS | {"vinnare"}

    def __init__(
        self,
        client: ATGClient | None = None,
        products: Iterable[str] | None = None,
    ) -> None:
        self._client = client or ATGClient()
        self._client_owned = client is None
        self._products = frozenset(products) if products else self.DEFAULT_PRODUCTS
        # Cache över country-koder som finns i databasen (laddas lazy)
        self._known_countries: set[str] | None = None

    async def close(self) -> None:
        if self._client_owned:
            await self._client.close()

    async def __aenter__(self) -> "AtgAdapter":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ---------- SourceAdapter interface ----------

    async def list_meetings(self, day: date) -> list[dict[str, Any]]:
        calendar = await self._client.calendar_day(day)
        results: list[dict[str, Any]] = []
        for product, games in calendar.games.items():
            if product not in self._products:
                continue
            for game in games:
                results.append(
                    {
                        "external_id": game.id,
                        "product": product,
                        "status": game.status,
                    }
                )
        return results

    async def fetch_meeting(self, external_id: str) -> dict[str, Any]:
        return await self._client.game_raw(external_id)

    def ingest_meeting(self, session: Session, raw_data: dict[str, Any]) -> dict[str, int]:
        counts = {
            "tracks": 0,
            "meetings": 0,
            "races": 0,
            "starts": 0,
            "horses": 0,
            "persons": 0,
            "odds_snapshots": 0,
            "equipment_changes": 0,
        }

        game_id = raw_data.get("id")
        if not game_id:
            raise ValueError(f"Game saknar id, keys={list(raw_data.keys())}")

        logger.info("ingest_game_start", game_id=game_id)

        self._save_raw_payload(session, "game", game_id, raw_data)

        for race_data in raw_data.get("races", []):
            try:
                self._ingest_race(session, race_data, counts)
            except ValueError as exc:
                logger.warning(
                    "race_skipped",
                    game_id=game_id,
                    race_id=race_data.get("id", "?"),
                    reason=str(exc),
                )
                continue

        logger.info("ingest_game_done", game_id=game_id, **counts)
        return counts

    # ---------- Internt: huvudflöde ----------

    def _ingest_race(
        self, session: Session, race_data: dict[str, Any], counts: dict[str, int]
    ) -> Race:
        if not race_data.get("id"):
            raise ValueError("Race saknar id")

        track_data = race_data.get("track")
        if not track_data or not track_data.get("id"):
            raise ValueError(f"Race {race_data['id']} saknar track-data eller track-id")

        track = self._upsert_track(session, track_data, counts)

        race_date = self._parse_date(race_data.get("date"))
        if race_date is None:
            raise ValueError(f"Race {race_data['id']} saknar datum")

        meeting = self._upsert_meeting(session, track, race_date, counts)
        race = self._upsert_race(session, meeting, race_data, counts)

        for start_data in race_data.get("starts", []):
            try:
                self._ingest_start(session, race, start_data, counts)
            except ValueError as exc:
                logger.warning(
                    "start_skipped",
                    race_id=race_data["id"],
                    start_id=start_data.get("id", "?"),
                    reason=str(exc),
                )
                continue

        return race

    def _ingest_start(
        self, session: Session, race: Race, start_data: dict[str, Any], counts: dict[str, int]
    ) -> Start:
        if not start_data.get("id"):
            raise ValueError("Start saknar id")

        horse_data = start_data.get("horse")
        if not horse_data or not horse_data.get("id"):
            raise ValueError(f"Start {start_data['id']} saknar horse-data eller horse-id")

        horse = self._upsert_horse(session, horse_data, counts)

        rider = self._upsert_person(session, start_data.get("driver"), counts)
        trainer = self._upsert_person(session, horse_data.get("trainer"), counts)

        start = self._upsert_start(session, race, horse, rider, trainer, start_data, counts)

        self._upsert_odds_snapshots(session, start, start_data, counts)
        self._upsert_equipment_changes(session, start, start_data, counts)

        return start

    # ---------- Country resolution ----------

    def _resolve_country_code(self, session: Session, raw_code: str | None) -> str:
        """Validera country_code mot countries-tabellen.

        Faller tillbaka till FALLBACK_COUNTRY (ZZ) om koden inte finns. Detta
        gör adaptern robust mot internationella banor som dyker upp i ATG
        utan att vi har dem i countries-seed.
        """
        if not raw_code:
            return FALLBACK_COUNTRY

        normalized = raw_code.upper()

        # Lazy-init: läs alla kända country-koder en gång per adapter-instans
        if self._known_countries is None:
            self._known_countries = set(session.execute(select(Country.code)).scalars().all())

        if normalized in self._known_countries:
            return normalized

        logger.warning(
            "unknown_country_fallback",
            requested=normalized,
            fallback=FALLBACK_COUNTRY,
        )
        return FALLBACK_COUNTRY

    # ---------- ExternalId helpers ----------

    def _find_external(
        self, session: Session, entity_type: str, external_id: str
    ) -> ExternalId | None:
        return session.execute(
            select(ExternalId).where(
                ExternalId.source_code == SOURCE_CODE,
                ExternalId.entity_type == entity_type,
                ExternalId.external_id == external_id,
            )
        ).scalar_one_or_none()

    def _register_external(
        self, session: Session, entity_type: str, external_id: str, internal_id: UUID
    ) -> None:
        today = date.today()
        session.add(
            ExternalId(
                source_code=SOURCE_CODE,
                entity_type=entity_type,
                external_id=external_id,
                internal_id=internal_id,
                first_seen_at=today,
                last_seen_at=today,
            )
        )
        session.flush()

    # ---------- Track ----------

    def _upsert_track(
        self, session: Session, track_data: dict[str, Any], counts: dict[str, int]
    ) -> Track:
        atg_id = str(track_data["id"])
        external = self._find_external(session, "track", atg_id)

        country_code = self._resolve_country_code(session, track_data.get("countryCode"))

        if external:
            external.last_seen_at = date.today()
            track = session.get(Track, external.internal_id)
            if track is None:
                raise RuntimeError(f"Track {atg_id} mappad men hittas inte i tabellen")
            track.name = track_data.get("name") or track.name
            track.country_code = country_code
            return track

        track = Track(
            id=uuid4(),
            name=track_data.get("name") or f"ATG track {atg_id}",
            country_code=country_code,
        )
        session.add(track)
        session.flush()
        self._register_external(session, "track", atg_id, track.id)
        counts["tracks"] += 1
        return track

    # ---------- Meeting ----------

    def _upsert_meeting(
        self, session: Session, track: Track, meeting_date: date, counts: dict[str, int]
    ) -> Meeting:
        external_id = f"{track.id}_{meeting_date.isoformat()}"
        external = self._find_external(session, "meeting", external_id)

        if external:
            external.last_seen_at = date.today()
            meeting = session.get(Meeting, external.internal_id)
            if meeting is None:
                raise RuntimeError(f"Meeting {external_id} mappad men hittas inte")
            return meeting

        meeting = Meeting(
            id=uuid4(),
            track_id=track.id,
            date=meeting_date,
            session=1,
            currency_code="SEK",
        )
        session.add(meeting)
        session.flush()
        self._register_external(session, "meeting", external_id, meeting.id)
        counts["meetings"] += 1
        return meeting

    # ---------- Race ----------

    def _upsert_race(
        self,
        session: Session,
        meeting: Meeting,
        race_data: dict[str, Any],
        counts: dict[str, int],
    ) -> Race:
        atg_id = race_data["id"]
        external = self._find_external(session, "race", atg_id)

        result = race_data.get("result") or {}
        race_kwargs = {
            "meeting_id": meeting.id,
            "discipline_code": "trot_sulky",
            "number": race_data.get("number") or 0,
            "name": race_data.get("name"),
            "distance_m": race_data.get("distance"),
            "start_method": START_METHOD_MAP.get(race_data.get("startMethod") or ""),
            "scheduled_start_time": self._parse_datetime(race_data.get("scheduledStartTime")),
            "actual_start_time": self._parse_datetime(race_data.get("startTime")),
            "status": race_data.get("status"),
            "track_condition": (race_data.get("track") or {}).get("condition"),
            "prize_text": race_data.get("prize"),
            "victory_margin": result.get("victoryMargin"),
            "scratchings": result.get("scratchings"),
        }

        if external:
            external.last_seen_at = date.today()
            race = session.get(Race, external.internal_id)
            if race is None:
                raise RuntimeError(f"Race {atg_id} mappad men hittas inte")
            for k, v in race_kwargs.items():
                if v is not None:
                    setattr(race, k, v)
            return race

        race = Race(id=uuid4(), **race_kwargs)
        session.add(race)
        session.flush()
        self._register_external(session, "race", atg_id, race.id)
        counts["races"] += 1
        return race

    # ---------- Horse ----------

    def _upsert_horse(
        self, session: Session, horse_data: dict[str, Any], counts: dict[str, int]
    ) -> Horse:
        atg_id = str(horse_data["id"])
        external = self._find_external(session, "horse", atg_id)

        pedigree = horse_data.get("pedigree") or {}
        father_id = self._upsert_pedigree_horse(session, pedigree.get("father"), counts)
        mother_id = self._upsert_pedigree_horse(session, pedigree.get("mother"), counts)

        owner = horse_data.get("owner") or {}
        breeder = horse_data.get("breeder") or {}

        horse_kwargs = {
            "name": horse_data.get("name") or f"ATG horse {atg_id}",
            "sex": horse_data.get("sex"),
            "color": horse_data.get("color"),
            "father_id": father_id,
            "mother_id": mother_id,
            "last_known_owner": owner.get("name"),
            "last_known_breeder": breeder.get("name"),
            "career_earnings_minor": horse_data.get("money"),
        }
        if horse_data.get("age"):
            horse_kwargs["birth_year"] = date.today().year - int(horse_data["age"])

        if external:
            external.last_seen_at = date.today()
            horse = session.get(Horse, external.internal_id)
            if horse is None:
                raise RuntimeError(f"Horse {atg_id} mappad men hittas inte")
            for k, v in horse_kwargs.items():
                if v is not None:
                    setattr(horse, k, v)
            return horse

        horse = Horse(id=uuid4(), **horse_kwargs)
        session.add(horse)
        session.flush()
        self._register_external(session, "horse", atg_id, horse.id)
        counts["horses"] += 1
        return horse

    def _upsert_pedigree_horse(
        self, session: Session, parent: dict[str, Any] | None, counts: dict[str, int]
    ) -> UUID | None:
        if not parent or not parent.get("id"):
            return None
        atg_id = str(parent["id"])
        external = self._find_external(session, "horse", atg_id)
        if external:
            return external.internal_id

        horse = Horse(
            id=uuid4(),
            name=parent.get("name") or f"ATG horse {atg_id}",
            country_of_birth=parent.get("nationality"),
        )
        session.add(horse)
        session.flush()
        self._register_external(session, "horse", atg_id, horse.id)
        counts["horses"] += 1
        return horse.id

    # ---------- Person ----------

    def _upsert_person(
        self, session: Session, person_data: dict[str, Any] | None, counts: dict[str, int]
    ) -> Person | None:
        if not person_data or not person_data.get("id"):
            return None
        atg_id = str(person_data["id"])
        external = self._find_external(session, "person", atg_id)

        first = person_data.get("firstName")
        last = person_data.get("lastName")
        full_name = (
            " ".join(p for p in [first, last] if p) or person_data.get("shortName") or "Unknown"
        )

        person_kwargs = {
            "full_name": full_name,
            "first_name": first,
            "last_name": last,
            "short_name": person_data.get("shortName"),
            "birth_year": person_data.get("birth"),
            "location": person_data.get("location"),
            "license_type": person_data.get("license"),
            "country_code": "SE",
        }

        if external:
            external.last_seen_at = date.today()
            person = session.get(Person, external.internal_id)
            if person is None:
                raise RuntimeError(f"Person {atg_id} mappad men hittas inte")
            for k, v in person_kwargs.items():
                if v is not None:
                    setattr(person, k, v)
            return person

        person = Person(id=uuid4(), **person_kwargs)
        session.add(person)
        session.flush()
        self._register_external(session, "person", atg_id, person.id)
        counts["persons"] += 1
        return person

    # ---------- Start ----------

    def _upsert_start(
        self,
        session: Session,
        race: Race,
        horse: Horse,
        rider: Person | None,
        trainer: Person | None,
        start_data: dict[str, Any],
        counts: dict[str, int],
    ) -> Start:
        atg_id = start_data["id"]
        external = self._find_external(session, "start", atg_id)

        shoes = start_data.get("shoes") or {}
        front = shoes.get("front") or {}
        back = shoes.get("back") or {}
        sulky = start_data.get("sulky") or {}
        sulky_type = sulky.get("type") or {}

        result = start_data.get("result") or {}

        start_kwargs = {
            "race_id": race.id,
            "horse_id": horse.id,
            "rider_id": rider.id if rider else None,
            "trainer_id": trainer.id if trainer else None,
            "start_number": start_data.get("number") or 0,
            "post_position": start_data.get("postPosition"),
            "distance_m": start_data.get("distance"),
            "horse_age_at_start": (start_data.get("horse") or {}).get("age"),
            "horse_earnings_at_start_minor": (start_data.get("horse") or {}).get("money"),
            "is_scratched": False,
            "finish_position": result.get("place"),
            "finish_order": result.get("finishOrder"),
            "km_time_s": self._parse_km_time(result.get("kmTime")),
            "prize_money_minor": result.get("prizeMoney"),
            "final_win_odds": (
                Decimal(str(result["finalOdds"])) if result.get("finalOdds") else None
            ),
            "sulky_type": sulky_type.get("text"),
            "sulky_changed": sulky_type.get("changed"),
            "shoes_front": front.get("hasShoe"),
            "shoes_back": back.get("hasShoe"),
            "shoes_front_changed": front.get("changed"),
            "shoes_back_changed": back.get("changed"),
        }

        if external:
            external.last_seen_at = date.today()
            start = session.get(Start, external.internal_id)
            if start is None:
                raise RuntimeError(f"Start {atg_id} mappad men hittas inte")
            for k, v in start_kwargs.items():
                if v is not None:
                    setattr(start, k, v)
            return start

        start = Start(id=uuid4(), **start_kwargs)
        session.add(start)
        session.flush()
        self._register_external(session, "start", atg_id, start.id)
        counts["starts"] += 1
        return start

    # ---------- Odds ----------

    def _upsert_odds_snapshots(
        self,
        session: Session,
        start: Start,
        start_data: dict[str, Any],
        counts: dict[str, int],
    ) -> None:
        pools = start_data.get("pools") or {}
        captured = datetime.now(UTC)

        for code, pool in pools.items():
            if not isinstance(pool, dict):
                continue
            snapshot_kwargs = self._pool_to_snapshot_kwargs(code, pool)
            if snapshot_kwargs is None:
                continue
            snapshot = OddsSnapshot(
                start_id=start.id,
                bet_type_code=code.upper(),
                bet_type_operator=SOURCE_CODE,
                captured_at=captured,
                is_final=True,
                **snapshot_kwargs,
            )
            session.add(snapshot)
            counts["odds_snapshots"] += 1

    def _pool_to_snapshot_kwargs(self, code: str, pool: dict[str, Any]) -> dict[str, Any] | None:
        if "odds" in pool:
            return {
                "odds_decimal": Decimal(str(pool["odds"])) / 100,
            }
        if "minOdds" in pool and "maxOdds" in pool:
            return {
                "odds_decimal": Decimal(str(pool["minOdds"])) / 100,
                "odds_decimal_max": Decimal(str(pool["maxOdds"])) / 100,
            }
        if "betDistribution" in pool:
            return {
                "odds_decimal": Decimal("0"),
                "pool_share": Decimal(str(pool["betDistribution"])) / 1000,
            }
        return None

    # ---------- Equipment changes ----------

    def _upsert_equipment_changes(
        self,
        session: Session,
        start: Start,
        start_data: dict[str, Any],
        counts: dict[str, int],
    ) -> None:
        shoes = start_data.get("shoes") or {}
        front = shoes.get("front") or {}
        back = shoes.get("back") or {}
        sulky = start_data.get("sulky") or {}
        sulky_type = sulky.get("type") or {}

        if front.get("changed"):
            session.add(
                EquipmentChange(
                    start_id=start.id,
                    item="shoes_front",
                    change_type="changed_state",
                )
            )
            counts["equipment_changes"] += 1
        if back.get("changed"):
            session.add(
                EquipmentChange(
                    start_id=start.id,
                    item="shoes_back",
                    change_type="changed_state",
                )
            )
            counts["equipment_changes"] += 1
        if sulky_type.get("changed"):
            session.add(
                EquipmentChange(
                    start_id=start.id,
                    item="sulky",
                    change_type="changed_type",
                    notes=sulky_type.get("text"),
                )
            )
            counts["equipment_changes"] += 1

    # ---------- Raw ----------

    def _save_raw_payload(
        self, session: Session, entity_type: str, external_id: str, payload: dict[str, Any]
    ) -> None:
        session.add(
            RawPayload(
                source_code=SOURCE_CODE,
                entity_type=entity_type,
                external_id=external_id,
                fetched_at=datetime.now(UTC),
                payload=payload,
            )
        )

    # ---------- Hjälpare ----------

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            return None

    @staticmethod
    def _parse_km_time(value: dict[str, Any] | None) -> Decimal | None:
        if not value:
            return None
        minutes = value.get("minutes", 0) or 0
        seconds = value.get("seconds", 0) or 0
        tenths = value.get("tenths", 0) or 0
        return Decimal(minutes) * 60 + Decimal(seconds) + Decimal(tenths) / 10
