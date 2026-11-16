from kavzi_trader.archive.archive_dataset_schema import ArchiveDatasetSchema
from kavzi_trader.evals.candle_cache import COLUMNS as KLINE_COLUMNS
from kavzi_trader.evals.metrics_cache import (
    GLOBAL_RATIO,
    OPEN_INTEREST,
    TIME,
    TOP_POSITION_RATIO,
)

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
    # Ratio meanings were matched against the REST endpoints on 2026-11-16.
    "metrics": ArchiveDatasetSchema(
        name="metrics",
        daily=True,
        columns=[
            TIME,
            OPEN_INTEREST,
            "open_interest_value",
            "top_account_ratio",
            TOP_POSITION_RATIO,
            GLOBAL_RATIO,
            "taker_volume_ratio",
        ],
        source_columns=[
            "create_time",
            "sum_open_interest",
            "sum_open_interest_value",
            "count_toptrader_long_short_ratio",
            "sum_toptrader_long_short_ratio",
            "count_long_short_ratio",
            "sum_taker_long_short_vol_ratio",
        ],
    ),
}
