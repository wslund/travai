"""HTTP-klient mot ATG:s inofficiella racinginfo-API.

OBS: Detta API är inte officiellt dokumenterat. Det är publikt åtkomligt
och används av ATG:s egen webbplats. Var snäll mot det - rate limiting,
realistiska User-Agent, och respektera 429-svar.

För produktion ska du skaffa partneravtal med ATG och använda AIS istället.
"""

import asyncio
from datetime import date
from types import TracebackType
from typing import Any, Self

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from travai.config import settings
from travai.logging_setup import get_logger
from travai.sources.atg.models import CalendarDay, Game

logger = get_logger(__name__)


class ATGClient:
    """Asynkron klient mot ATG:s racinginfo-API."""

    def __init__(
        self,
        base_url: str | None = None,
        rate_limit_seconds: float | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url or settings.atg_base_url
        self.rate_limit_seconds = (
            rate_limit_seconds
            if rate_limit_seconds is not None
            else settings.atg_rate_limit_seconds
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "User-Agent": settings.atg_user_agent,
                "Accept": "application/json",
            },
            follow_redirects=True,
        )
        self._last_request_at: float = 0.0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        """Säkerställ att vi inte hamrar API:t."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_at
            if elapsed < self.rate_limit_seconds:
                await asyncio.sleep(self.rate_limit_seconds - elapsed)
            self._last_request_at = asyncio.get_event_loop().time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def _get(self, path: str) -> dict[str, Any]:
        await self._throttle()
        logger.debug("atg_request", path=path)
        response = await self._client.get(path)
        if response.status_code == 429:
            logger.warning("rate_limited", path=path)
            raise httpx.HTTPStatusError("Rate limited", request=response.request, response=response)
        response.raise_for_status()
        return response.json()

    async def calendar_day(self, day: date) -> CalendarDay:
        """Hämta dagens kalender - vilka spel och lopp som körs."""
        data = await self._get(f"/calendar/day/{day.isoformat()}")
        return CalendarDay.model_validate(data)

    async def game(self, game_id: str) -> Game:
        """Hämta detaljerad info om ett spel (t.ex. V75_2024-01-13_23_5)."""
        data = await self._get(f"/games/{game_id}")
        return Game.model_validate(data)

    async def game_raw(self, game_id: str) -> dict[str, Any]:
        """Som game() men returnerar rå JSON - bra under utforskning."""
        return await self._get(f"/games/{game_id}")
