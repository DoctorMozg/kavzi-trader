import logging
from datetime import UTC, datetime

import httpx

from kavzi_trader.external.base import ExternalSource
from kavzi_trader.external.schemas import FearGreedDataSchema

logger = logging.getLogger(__name__)

_FGI_URL = "https://api.alternative.me/fng/"
_TIMEOUT_S = 10.0


class FearGreedSource(ExternalSource):
    """Fetches the Crypto Fear & Greed Index from Alternative.me."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=_TIMEOUT_S)

    @property
    def name(self) -> str:
        return "fear_greed"

    async def fetch(self) -> FearGreedDataSchema | None:
        try:
            resp = await self._client.get(
                _FGI_URL,
                params={"limit": "1", "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            if not data:
                logger.warning("Fear & Greed API returned empty data array")
                return None
            entry = data[0]
            return FearGreedDataSchema(
                value=int(entry["value"]),
                classification=str(entry["value_classification"]),
                fetched_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception("Fear & Greed fetch failed")
            return None
