import logging
from collections import Counter
from datetime import datetime, timedelta

from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.strategies.trend.gate_inputs_schema import GateInputsSchema
from kavzi_trader.strategies.trend.trend_gate_config import TrendGateConfigSchema

logger = logging.getLogger(__name__)


class GateInputsReader:
    """Summarises the headline window the shadow gate reviews entries against."""

    def __init__(
        self, config: TrendGateConfigSchema, model_id: str, prompt_sha: str
    ) -> None:
        self._config = config
        self._model_id = model_id
        self._prompt_sha = prompt_sha

    def read(self, now: datetime) -> GateInputsSchema:
        # Reload each time: the collector appends from another process.
        items = NewsStore(self._config.news_root).query(
            now,
            timedelta(hours=self._config.window_h),
            timedelta(hours=self._config.lag_h),
        )
        coins = Counter(coin for item in items for coin in item.coins)
        logger.debug("Gate inputs: %d headlines in window", len(items))
        return GateInputsSchema(
            model_id=self._model_id,
            samples=self._config.samples,
            prompt_sha=self._prompt_sha,
            window_h=self._config.window_h,
            lag_h=self._config.lag_h,
            headlines=len(items),
            newest_at=items[0].published_at if items else None,
            coin_headlines=dict(coins),
        )
