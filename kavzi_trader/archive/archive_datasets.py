from kavzi_trader.archive.archive_dataset_schema import ArchiveDatasetSchema
from kavzi_trader.evals.candle_cache import COLUMNS as KLINE_COLUMNS

_KLINE = list(KLINE_COLUMNS)

ARCHIVE_DATASETS = {
    "klines": ArchiveDatasetSchema(name="klines", interval="1m", columns=_KLINE),
    "mark": ArchiveDatasetSchema(name="markPriceKlines", interval="1m", columns=_KLINE),
    "premium": ArchiveDatasetSchema(
        name="premiumIndexKlines", interval="1m", columns=_KLINE
    ),
    "funding": ArchiveDatasetSchema(
        name="fundingRate", columns=["time_ms", "interval_hours", "rate"]
    ),
}
