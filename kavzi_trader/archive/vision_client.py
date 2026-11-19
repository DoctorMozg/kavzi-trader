import httpx2

from kavzi_trader.commons.retry import RetryPolicySchema, retry_async

_SERVER_ERROR = 500
# data.binance.vision answers 503 under load; waits of 2, 4, 8 and 16 s ride it out.
VISION_RETRY_POLICY = RetryPolicySchema(
    attempts=5,
    backoff_base_s=2.0,
    retry_on=(httpx2.HTTPStatusError, httpx2.TransportError),
)


class VisionClient:
    """GETs from data.binance.vision, retrying 5xx answers and dropped connections.

    Any other answer, 404 included, goes back to the caller to interpret.
    """

    def __init__(
        self, http: httpx2.AsyncClient, policy: RetryPolicySchema = VISION_RETRY_POLICY
    ) -> None:
        self._http = http
        self._policy = policy

    async def get(
        self, url: str, params: dict[str, str] | None = None
    ) -> httpx2.Response:
        async def _once() -> httpx2.Response:
            response = await self._http.get(url, params=params)
            if response.status_code >= _SERVER_ERROR:
                response.raise_for_status()
            return response

        return await retry_async(_once, self._policy, name=f"GET {url}")
