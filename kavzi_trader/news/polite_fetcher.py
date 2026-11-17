import asyncio
import time
from urllib.parse import urlsplit

import httpx2

USER_AGENT = "KavziNewsBot/0.1 (personal research; rate-limited)"


class PoliteFetcher:
    """GETs pages with an honest user agent, spacing requests to each host."""

    def __init__(
        self,
        http: httpx2.AsyncClient,
        min_interval_s: float = 2.0,
        host_interval_s: dict[str, float] | None = None,
    ) -> None:
        self._http = http
        self._min_interval_s = min_interval_s
        self._host_interval_s = host_interval_s or {}
        self._last_request_s: dict[str, float] = {}

    async def get_text(self, url: str) -> str:
        host = urlsplit(url).netloc
        interval_s = self._host_interval_s.get(host, self._min_interval_s)
        wait_s = self._last_request_s.get(host, -interval_s) + interval_s
        delay_s = wait_s - time.monotonic()
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        self._last_request_s[host] = time.monotonic()
        response = await self._http.get(
            url, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        response.raise_for_status()
        return response.text
