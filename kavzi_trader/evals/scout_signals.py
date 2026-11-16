import logging
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from kavzi_trader.config import AppConfig
from kavzi_trader.domain.candlestick import CandlestickSchema
from kavzi_trader.evals.replay_kline_source import ReplayKlineSource
from kavzi_trader.evals.synthetic_account import EVAL_BALANCE_USDT, SyntheticAccount
from kavzi_trader.indicators.calculator import TechnicalIndicatorCalculator
from kavzi_trader.orchestrator.providers.live_dependencies_provider import (
    LiveDependenciesProvider,
)
from kavzi_trader.orchestrator.providers.market_data_cache import MarketDataCache
from kavzi_trader.spine.filters.confluence import ConfluenceCalculator
from kavzi_trader.spine.filters.scout import ScoutFilter
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from kavzi_trader.spine.risk.symbol_tier_registry import SymbolTierRegistry
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector

logger = logging.getLogger(__name__)

_TREND = "TREND_CONTINUATION"
_MS_PER_S = 1000


class ScoutSignals:
    """Replays the live Scout on sampled bars, once per trend volume threshold.

    ``scout_trend_<X>`` fires on the EMA-stack side when the Scout calls the
    bar INTERESTING through TREND_CONTINUATION with ``trend_vol_ratio_min=X``.
    The context is built as the live bot builds it, from the trailing window.
    """

    def __init__(
        self,
        app_config: AppConfig,
        tiers: SymbolTierRegistry,
        interval: str,
        vol_ratio_mins: list[Decimal],
    ) -> None:
        policy = RegimePolicy(
            app_config.risk, app_config.scout.extreme_allowed_patterns
        )
        self._config = app_config
        self._tiers = tiers
        self._interval = interval
        self._detector = VolatilityRegimeDetector(app_config.risk, policy)
        self._scouts = {
            scout_signal_name(v): ScoutFilter(
                app_config.scout.model_copy(update={"trend_vol_ratio_min": v}), policy
            )
            for v in vol_ratio_mins
        }

    @property
    def names(self) -> list[str]:
        return list(self._scouts)

    async def add(
        self, symbol: str, frame: pd.DataFrame, samples: pd.DataFrame
    ) -> pd.DataFrame:
        """``samples`` plus LONG_/SHORT_ columns for each Scout variant."""
        if samples.empty:
            return samples
        history = self._config.trading.history_candles
        idx = samples["idx"].to_numpy(dtype=np.int64)
        first = max(int(idx.min()) - history + 1, 0)
        candles = _candles(frame.iloc[first : int(idx.max()) + 1])
        fired = {n: np.zeros(len(idx), dtype=bool) for n in self._scouts}
        for row, i in enumerate(idx):
            window = candles[i - history + 1 - first : i + 1 - first]
            provider = await self._provider(symbol, window)
            deps = await provider.get_scout(symbol)
            for n, scout in self._scouts.items():
                decision = await scout.run(deps)
                fired[n][row] = (
                    decision.verdict == "INTERESTING"
                    and decision.pattern_detected == _TREND
                )
        out = samples.copy()
        for n, hits in fired.items():
            # TREND_CONTINUATION needs a full EMA stack, the same stack as
            # the confluence ema_alignment flag, so that flag gives the side.
            out[f"LONG_{n}"] = hits & out["LONG_ema_alignment"].to_numpy(dtype=bool)
            out[f"SHORT_{n}"] = hits & out["SHORT_ema_alignment"].to_numpy(dtype=bool)
            logger.debug(
                "%s %s fired on %d of %d bars", symbol, n, hits.sum(), len(idx)
            )
        return out

    async def _provider(
        self, symbol: str, window: list[CandlestickSchema]
    ) -> LiveDependenciesProvider:
        cache = MarketDataCache([symbol], TechnicalIndicatorCalculator(), len(window))
        await cache.initialize(ReplayKlineSource(window), self._interval)
        return LiveDependenciesProvider(
            cache=cache,
            confluence_calculator=ConfluenceCalculator(),
            volatility_detector=self._detector,
            state_manager=SyntheticAccount(EVAL_BALANCE_USDT, window[-1].close_time),
            timeframe=self._interval,
            futures_config=self._config.futures,
            tier_registry=self._tiers,
        )


def scout_signal_name(vol_ratio_min: Decimal) -> str:
    return f"scout_trend_{vol_ratio_min}"


def _candles(frame: pd.DataFrame) -> list[CandlestickSchema]:
    def at(ms: int) -> datetime:
        return datetime.fromtimestamp(ms / _MS_PER_S, UTC)

    return [
        CandlestickSchema(
            open_time=at(int(r.open_time_ms)),
            open_price=Decimal(str(r.open)),
            high_price=Decimal(str(r.high)),
            low_price=Decimal(str(r.low)),
            close_price=Decimal(str(r.close)),
            volume=Decimal(str(r.volume)),
            close_time=at(int(r.close_time_ms)),
            quote_volume=Decimal(str(r.quote_volume)),
            trades_count=int(r.trades_count),
            taker_buy_base_volume=Decimal(str(r.taker_buy_base_volume)),
            taker_buy_quote_volume=Decimal(str(r.taker_buy_quote_volume)),
        )
        for r in frame.itertuples()
    ]
