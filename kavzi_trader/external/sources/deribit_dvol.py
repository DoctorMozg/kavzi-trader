import json
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx2

from kavzi_trader.commons.retry import RetryPolicySchema, retry_async
from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.schemas import DeribitDvolDataSchema

logger = logging.getLogger(__name__)

_DERIBIT_BASE = "https://www.deribit.com/api/v2/public"
_DVOL_URL = f"{_DERIBIT_BASE}/get_index_price"
_BOOK_SUMMARY_URL = f"{_DERIBIT_BASE}/get_book_summary_by_currency"
_TIMEOUT_S = 15.0
_ZERO = Decimal(0)
# 3 attempts, waiting 1s then 2s between them.
_RETRY_POLICY = RetryPolicySchema(
    attempts=3,
    backoff_base_s=1.0,
    retry_on=(httpx2.HTTPStatusError, httpx2.TimeoutException),
    strategy="linear",
)


class DeribitDvolSource(ExternalSource):
    """Fetches BTC DVOL index and put/call ratio from Deribit public API."""

    def __init__(self) -> None:
        self._client = httpx2.AsyncClient(timeout=_TIMEOUT_S)

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
        except (
            httpx2.RequestError,
            httpx2.HTTPStatusError,
            httpx2.TimeoutException,
            json.JSONDecodeError,
            ValueError,
            KeyError,
            TypeError,
            InvalidOperation,
        ):
            logger.exception("Deribit DVOL fetch failed")
            return None

    async def _get_with_retry(
        self,
        url: str,
        params: dict[str, str],
    ) -> httpx2.Response:
        """GET with retry on transient HTTP/timeout errors."""

        async def _get() -> httpx2.Response:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            return resp

        return await retry_async(_get, _RETRY_POLICY, name=f"Deribit request to {url}")

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
