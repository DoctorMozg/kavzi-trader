import logging
from collections import Counter
from datetime import datetime, timedelta

from kavzi_trader.news.news_store import NewsStore
from kavzi_trader.strategies.trend.gate_inputs_schema import GateInputsSchema
from kavzi_trader.strategies.trend.trend_gate_config import TrendGateConfigSchema
from kavzi_trader.strategies.trend.trend_gate_log import TrendGateLog

logger = logging.getLogger(__name__)


class GateInputsReader:
    """Summarises the gate's headline window and its live review log so far."""

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
        # A new prompt is a new trial, so only its own reviews count.
        reviews = [
            r
            for r in TrendGateLog(self._config.log_path).read()
            if r.prompt_sha == self._prompt_sha
        ]
        logger.debug(
            "Gate inputs: %d headlines in window, %d reviews logged",
            len(items),
            len(reviews),
        )
        return GateInputsSchema(
            model_id=self._model_id,
            samples=self._config.samples,
            prompt_sha=self._prompt_sha,
            window_h=self._config.window_h,
            lag_h=self._config.lag_h,
            headlines=len(items),
            newest_at=items[0].published_at if items else None,
            coin_headlines=dict(coins),
            reviews=len(reviews),
            vetoes=sum(r.decision == "VETO" for r in reviews),
        )
