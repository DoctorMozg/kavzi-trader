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
_ZERO = Decimal(0)


class DeribitDvolSource(ExternalSource):
    """Fetches BTC DVOL index and put/call ratio from Deribit public API."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=_TIMEOUT_S)

    @property
    def name(self) -> str:
        return "deribit_dvol"

    async def fetch(self) -> DeribitDvolDataSchema | None:
        try:
            dvol_index = await self._fetch_dvol()
            btc_pc_ratio = await self._fetch_put_call_ratio()
            return DeribitDvolDataSchema(
                dvol_index=dvol_index,
                btc_put_call_ratio=btc_pc_ratio,
                eth_put_call_ratio=None,
                fetched_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception("Deribit DVOL fetch failed")
            return None

    async def _fetch_dvol(self) -> Decimal:
        resp = await self._client.get(
            _DVOL_URL,
            params={"index_name": "btcdvol_usdc"},
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        return Decimal(str(result["index_price"]))

    async def _fetch_put_call_ratio(self) -> Decimal:
        resp = await self._client.get(
            _BOOK_SUMMARY_URL,
            params={"currency": "BTC", "kind": "option"},
        )
        resp.raise_for_status()
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
