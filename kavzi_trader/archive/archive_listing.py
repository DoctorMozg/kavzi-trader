import logging
import xml.etree.ElementTree as ET

from kavzi_trader.archive.archive_dataset_schema import ArchiveDatasetSchema
from kavzi_trader.archive.vision_client import VisionClient

logger = logging.getLogger(__name__)

LISTING_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


class ArchiveListing:
    """Lists what data.binance.vision holds, following S3's 1000-entry pages."""

    def __init__(self, http: VisionClient) -> None:
        self._http = http

    async def periods(self, dataset: ArchiveDatasetSchema, symbol: str) -> list[str]:
        """YYYY-MM months, or YYYY-MM-DD days for a daily dataset, with a zip."""
        prefix = f"{dataset.prefix}{dataset.symbol_dir(symbol)}/"
        head = prefix + dataset.file_stem(symbol, "")
        keys = await self._list(prefix)
        return sorted(
            k.removeprefix(head).removesuffix(".zip")
            for k in keys
            if k.startswith(head) and k.endswith(".zip")
        )

    async def _list(self, prefix: str) -> list[str]:
        found: list[str] = []
        marker = ""
        while True:
            params = {"prefix": prefix, "marker": marker}
            response = await self._http.get(LISTING_URL, params=params)
            response.raise_for_status()
            root = ET.fromstring(response.content)  # noqa: S314 - S3 listing XML
            page = [e.text for e in root.findall("s3:Contents/s3:Key", _NS) if e.text]
            found.extend(page)
            if root.findtext("s3:IsTruncated", namespaces=_NS) != "true" or not page:
                break
            marker = root.findtext("s3:NextMarker", namespaces=_NS) or page[-1]
        logger.debug("Listed %d entries under %s", len(found), prefix)
        return found
