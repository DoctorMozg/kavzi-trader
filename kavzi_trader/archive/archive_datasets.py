from kavzi_trader.archive.archive_dataset_schema import ArchiveDatasetSchema

# Stored column names are the on-disk Parquet format; renaming one orphans the mirror.
_KLINE = [
    "open_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time_ms",
    "quote_volume",
    "trades_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
]

ARCHIVE_DATASETS = {
    "klines": ArchiveDatasetSchema(name="klines", interval="1m", columns=_KLINE),
    # Daily bars only, for wide universes where 1m history would be tens of GB.
    "klines_1d": ArchiveDatasetSchema(name="klines", interval="1d", columns=_KLINE),
    # Hourly bars, the base of the 4h/6h/12h bars of the trend timing test.
    "klines_1h": ArchiveDatasetSchema(name="klines", interval="1h", columns=_KLINE),
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
            "time_ms",
            "open_interest",
            "open_interest_value",
            "top_account_ratio",
            "top_position_ratio",
            "global_ratio",
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
