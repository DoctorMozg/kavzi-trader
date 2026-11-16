import hashlib
import io
import zipfile

import httpx2
import pytest

from kavzi_trader.archive.archive_datasets import ARCHIVE_DATASETS

KLINE_HEADER = (
    "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
    "taker_buy_volume,taker_buy_quote_volume,ignore"
)

METRICS_HEADER = (
    "create_time,symbol,sum_open_interest,sum_open_interest_value,"
    "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
    "count_long_short_ratio,sum_taker_long_short_vol_ratio"
)


def kline_csv(first_ms: int, *, header: bool) -> str:
    rows = [
        f"{first_ms + i * 60_000},1.0,2.0,0.5,1.5,10,{first_ms + i * 60_000 + 59_999},"
        "15,3,4,6,0"
        for i in range(3)
    ]
    return "\n".join([KLINE_HEADER, *rows] if header else rows)


def zipped(member: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, text)
    return buffer.getvalue()


class FakeVision:
    """Serves S3 listings, zips and CHECKSUM files the way data.binance.vision does."""

    def __init__(self, page_size: int = 1000) -> None:
        self.files: dict[str, bytes] = {}
        self.checksums: dict[str, str] = {}
        self.downloads: list[str] = []
        self._page_size = page_size

    def add(self, key: str, member: str, text: str) -> None:
        content = zipped(member, text)
        self.files[key] = content
        digest = hashlib.sha256(content).hexdigest()
        self.checksums[key] = f"{digest}  {key.rsplit('/', 1)[-1]}"

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path.lstrip("/")
        if request.url.host.startswith("s3-"):
            return self._listing(request)
        if path.endswith(".CHECKSUM"):
            return httpx2.Response(
                200, text=self.checksums[path.removesuffix(".CHECKSUM")]
            )
        self.downloads.append(path)
        return httpx2.Response(200, content=self.files[path])

    def _listing(self, request: httpx2.Request) -> httpx2.Response:
        prefix = request.url.params["prefix"]
        marker = request.url.params.get("marker", "")
        delimiter = request.url.params.get("delimiter")
        keys = sorted(k for k in self.files if k.startswith(prefix))
        if delimiter:
            entries = sorted(
                {prefix + k.removeprefix(prefix).split("/")[0] + "/" for k in keys}
            )
            tag = "<CommonPrefixes><Prefix>{}</Prefix></CommonPrefixes>"
        else:
            entries = [e for k in keys for e in (k, k + ".CHECKSUM")]
            tag = "<Contents><Key>{}</Key></Contents>"
        rest = [e for e in entries if e > marker]
        page = rest[: self._page_size]
        truncated = len(rest) > len(page)
        body = "".join(tag.format(e) for e in page)
        nxt = f"<NextMarker>{page[-1]}</NextMarker>" if truncated and delimiter else ""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<IsTruncated>{str(truncated).lower()}</IsTruncated>{nxt}{body}"
            "</ListBucketResult>"
        )
        return httpx2.Response(200, content=xml.encode())


def kline_key(symbol: str, month: str) -> str:
    klines = ARCHIVE_DATASETS["klines"]
    stem = klines.file_stem(symbol, month)
    return f"{klines.prefix}{klines.symbol_dir(symbol)}/{stem}.zip"


def metrics_key(symbol: str, day: str) -> str:
    metrics = ARCHIVE_DATASETS["metrics"]
    stem = metrics.file_stem(symbol, day)
    return f"{metrics.prefix}{metrics.symbol_dir(symbol)}/{stem}.zip"


@pytest.fixture
def vision() -> FakeVision:
    return FakeVision(page_size=2)
