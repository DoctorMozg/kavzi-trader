import httpx2
import pytest

from kavzi_trader.archive.vision_client import VisionClient
from tests.archive.conftest import NO_WAIT

URL = "https://data.binance.vision/data/x.zip"


def _client(answers: list[int | Exception], calls: list[str]) -> VisionClient:
    """Answers each request with the next status, or raises the next error."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(str(request.url))
        answer = answers[min(len(calls), len(answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return httpx2.Response(answer, content=b"zip")

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return VisionClient(http, NO_WAIT)


class TestVisionClient:
    async def test_a_server_error_is_retried(self) -> None:
        calls: list[str] = []

        response = await _client([503, 200], calls).get(URL)

        assert response.status_code == 200
        assert response.content == b"zip"
        assert len(calls) == 2

    async def test_a_dropped_connection_is_retried(self) -> None:
        calls: list[str] = []
        dropped = httpx2.ConnectError("reset")

        response = await _client([dropped, 200], calls).get(URL)

        assert response.status_code == 200

    async def test_a_missing_file_is_returned_without_retry(self) -> None:
        calls: list[str] = []

        response = await _client([404], calls).get(URL)

        assert response.status_code == 404
        assert len(calls) == 1

    async def test_gives_up_after_the_last_attempt(self) -> None:
        calls: list[str] = []

        with pytest.raises(httpx2.HTTPStatusError, match="503"):
            await _client([503], calls).get(URL)
        assert len(calls) == 3

    async def test_passes_query_params(self) -> None:
        calls: list[str] = []

        await _client([200], calls).get(URL, params={"prefix": "a/"})

        assert calls == [f"{URL}?prefix=a%2F"]
