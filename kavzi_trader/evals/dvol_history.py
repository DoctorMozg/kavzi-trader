import logging
from pathlib import Path

import httpx2
import pandas as pd

from kavzi_trader.commons.retry import RetryPolicySchema, retry_async
from kavzi_trader.evals.dvol_page import DvolPage

logger = logging.getLogger(__name__)

DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
DVOL_DIR = Path("evals/dvol")
_MS_PER_DAY = 86_400_000
_RETRY = RetryPolicySchema(
    attempts=4,
    backoff_base_s=2.0,
    retry_on=(httpx2.HTTPStatusError, httpx2.TransportError),
)


class DvolHistory:
    """Deribit's daily DVOL (30-day implied vol index, percent) per currency."""

    def __init__(self, http: httpx2.AsyncClient) -> None:
        self._http = http

    async def download(self, currency: str, start_ms: int, end_ms: int) -> pd.Series:
        """Daily closes, indexed by the UTC day whose end they mark."""
        rows: list[list[float]] = []
        cursor = end_ms
        while cursor > start_ms:
            page = await self._page(currency, start_ms, cursor)
            rows.extend(page["data"])
            nxt = page.get("continuation")
            if not page["data"] or nxt is None or nxt >= cursor:
                break
            cursor = int(nxt)
        frame = pd.DataFrame(rows, columns=["open_ms", "open", "high", "low", "close"])
        frame = frame.drop_duplicates("open_ms").sort_values("open_ms")
        day = pd.to_datetime(frame["open_ms"] // _MS_PER_DAY, unit="D")
        logger.info("DVOL %s: %d daily closes", currency, len(frame))
        return pd.Series(frame["close"].to_numpy(dtype=float), index=day, name=currency)

    async def _page(self, currency: str, start_ms: int, end_ms: int) -> DvolPage:
        params = {
            "currency": currency,
            "start_timestamp": str(start_ms),
            "end_timestamp": str(end_ms),
            "resolution": "1D",
        }

        async def _once() -> DvolPage:
            response = await self._http.get(DVOL_URL, params=params)
            response.raise_for_status()
            result: DvolPage = response.json()["result"]
            return result

        return await retry_async(_once, _RETRY, name=f"DVOL {currency}")

    @staticmethod
    def save(series: pd.Series, directory: Path = DVOL_DIR) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{series.name}_daily.csv"
        series.rename("dvol").rename_axis("day").to_csv(path)
        return path

    @staticmethod
    def load(currency: str, directory: Path = DVOL_DIR) -> pd.Series:
        frame = pd.read_csv(directory / f"{currency}_daily.csv", parse_dates=["day"])
        return pd.Series(
            frame["dvol"].to_numpy(dtype=float),
            index=pd.DatetimeIndex(frame["day"]),
            name=currency,
        )
