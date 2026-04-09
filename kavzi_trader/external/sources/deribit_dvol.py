import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.schemas import DeribitDvolDataSchema

logger = logging.getLogger(__name__)

_DERIBIT_BASE = "https://www.deribit.com/api/v2/public"
_DVOL_URL = f"{_DERIBIT_BASE}/get_index_price"
_BOOK_SUMMARY_URL = f"{_DERIBIT_BASE}/get_book_summary_by_currency"
_TIMEOUT_S = 15.0
_MAX_RETRIES = 2
_RETRY_BACKOFF_S = 1.0
_ZERO = Decimal(0)


class DeribitDvolSource(ExternalSource):
    """Fetches BTC DVOL index and put/call ratio from Deribit public API."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=_TIMEOUT_S)

    @property
    def name(self) -> str:
        return "deribit_dvol"

    async def fetch(self) -> DeribitDvolDataSchema | None:
        logger.info("Fetching Deribit DVOL + put/call ratio")
        try:
            dvol_index = await self._fetch_dvol()
            btc_pc_ratio = await self._fetch_put_call_ratio()
            logger.info(
                "Deribit DVOL fetched: dvol=%.1f put_call_ratio=%.3f",
                dvol_index,
                btc_pc_ratio,
                extra={
                    "dvol_index": float(dvol_index),
                    "btc_put_call_ratio": float(btc_pc_ratio),
                },
            )
            return DeribitDvolDataSchema(
                dvol_index=dvol_index,
                btc_put_call_ratio=btc_pc_ratio,
                eth_put_call_ratio=None,
                fetched_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception("Deribit DVOL fetch failed")
            return None

    async def _get_with_retry(
        self,
        url: str,
        params: dict[str, str],
    ) -> httpx.Response:
        """GET with simple retry on transient HTTP/timeout errors."""
        last_exc: httpx.HTTPStatusError | httpx.TimeoutException | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await self._client.get(url, params=params)
                resp.raise_for_status()
            except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BACKOFF_S * (attempt + 1)
                    logger.warning(
                        "Deribit request to %s failed (attempt %d/%d), "
                        "retrying in %.1fs: %s",
                        url,
                        attempt + 1,
                        _MAX_RETRIES + 1,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
            else:
                return resp
        raise last_exc  # type: ignore[misc]

    async def _fetch_dvol(self) -> Decimal:
        resp = await self._get_with_retry(
            _DVOL_URL,
            params={"index_name": "btcdvol_usdc"},
        )
        result = resp.json()["result"]
        return Decimal(str(result["index_price"]))

    async def _fetch_put_call_ratio(self) -> Decimal:
        resp = await self._get_with_retry(
            _BOOK_SUMMARY_URL,
            params={"currency": "BTC", "kind": "option"},
        )
        summaries: list[dict[str, object]] = resp.json()["result"]

        put_oi = _ZERO
        call_oi = _ZERO
        for summary in summaries:
            instrument = str(summary.get("instrument_name", ""))
            oi = Decimal(str(summary.get("open_interest", 0)))
            if instrument.endswith("-P"):
                put_oi += oi
            elif instrument.endswith("-C"):
                call_oi += oi

        if call_oi == _ZERO:
            return _ZERO
        return put_oi / call_oi
