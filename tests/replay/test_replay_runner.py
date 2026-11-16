from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import pytest_asyncio

from kavzi_trader.cli.replay_composition import ReplayComposer, replay_costs
from kavzi_trader.config import AppConfig
from kavzi_trader.domain.symbol_filters import SymbolFiltersSchema
from kavzi_trader.evals.candle_cache import COLUMNS, CandleCache
from kavzi_trader.evals.series_cache import SeriesCache
from kavzi_trader.evals.trend_data_loader import TrendDataLoader
from kavzi_trader.evals.trend_metrics import TrendMetrics
from kavzi_trader.evals.trend_portfolio import TrendPortfolio
from kavzi_trader.replay.historical_daily_closes import HistoricalDailyCloses
from kavzi_trader.replay.replay_data_loader import ReplayDataLoader
from kavzi_trader.replay.replay_needs_schema import ReplayNeedsSchema
from kavzi_trader.replay.replay_result_schema import ReplayResultSchema
from kavzi_trader.replay.replay_runner import ReplayRunner
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from kavzi_trader.strategies.trend.donchian_trend_signal import DonchianTrendSignal
from kavzi_trader.strategies.trend.trend_params_schema import TrendParamsSchema
from kavzi_trader.strategies.trend.turnover_buffer import TurnoverBuffer

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
NEEDS = ReplayNeedsSchema(symbols=SYMBOLS, interval="4h", daily_closes=True)
BAR_MS = 4 * 3_600_000
FIRST_BAR_MS = 1_609_459_200_000  # 2021-01-01
DAYS = 360
START = pd.Timestamp("2021-04-01")
END = pd.Timestamp("2021-12-20")
FUNDING_RATE = 0.0001
TAKER_FEE = Decimal("0.0005")

pytestmark = pytest.mark.asyncio(loop_scope="module")


def _regime_closes() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(7)
    n_bars = DAYS * 6
    # Regime drifts so the trend rule goes in and out of the market.
    drift = np.where((np.arange(n_bars) // 300) % 2 == 0, 0.003, -0.002)
    return {
        symbol: 100 * (i + 1) * np.exp(np.cumsum(drift + rng.normal(0, 0.012, n_bars)))
        for i, symbol in enumerate(SYMBOLS)
    }


def _write_cache(cache_dir: Path, closes: dict[str, np.ndarray]) -> None:
    for symbol, close in closes.items():
        open_ms = FIRST_BAR_MS + np.arange(len(close)) * BAR_MS
        open_ = np.concatenate([[close[0]], close[:-1]])
        frame = pd.DataFrame(
            {
                "open_time_ms": open_ms,
                "open": open_,
                "high": np.maximum(open_, close) * 1.002,
                "low": np.minimum(open_, close) * 0.998,
                "close": close,
                "volume": 1.0,
                "close_time_ms": open_ms + BAR_MS - 1,
                "quote_volume": 1.0,
                "trades_count": 1,
                "taker_buy_base_volume": 0.5,
                "taker_buy_quote_volume": 0.5,
            },
            columns=list(COLUMNS),
        )
        frame.to_csv(CandleCache(cache_dir, "4h").path(symbol), compression="gzip")
        settle_ms = FIRST_BAR_MS + np.arange(len(close) // 2) * 8 * 3_600_000
        pd.DataFrame({"time_ms": settle_ms + 2, "value": FUNDING_RATE}).to_csv(
            SeriesCache(cache_dir, "funding").path(symbol),
            index=False,
            compression="gzip",
        )


def _precision() -> SymbolPrecision:
    return SymbolPrecision(
        SymbolFiltersSchema(
            symbol=symbol,
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            max_qty=Decimal(100_000),
            market_step_size=Decimal("0.001"),
            market_min_qty=Decimal("0.001"),
            market_max_qty=Decimal(100_000),
            tick_size=Decimal("0.01"),
            min_notional=Decimal(5),
        )
        for symbol in SYMBOLS
    )


def _ms(day: pd.Timestamp) -> int:
    return int(day.value // 1_000_000)


@pytest.fixture(scope="module")
def config(app_config: AppConfig) -> AppConfig:
    # At the default 5x a 30% disaster stop sits past liquidation and is rejected.
    futures = app_config.futures.model_copy(update={"default_leverage": 2})
    return app_config.model_copy(update={"futures": futures})


@pytest.fixture(scope="module")
def cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("replay_cache")
    _write_cache(path, _regime_closes())
    return path


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def replay(config: AppConfig, cache_dir: Path) -> ReplayResultSchema:
    data = ReplayDataLoader(cache_dir).load(NEEDS)
    composer = ReplayComposer(config, _precision(), replay_costs(TAKER_FEE, Decimal(0)))
    rig = await composer.compose("trend_following", data, _ms(START))
    runner = ReplayRunner(rig, data)
    return await runner.run(_ms(START), _ms(END))


@pytest.fixture(scope="module")
def reference(config: AppConfig, cache_dir: Path) -> pd.Series:
    """Daily net returns of the vectorized rule, labelled by the day they span."""
    trend = config.strategy.trend_following
    signal = DonchianTrendSignal(
        TrendParamsSchema(
            lookbacks=tuple(trend.lookbacks),
            vol_window=trend.vol_window,
            annual_vol_target=trend.annual_vol_target,
            max_leverage=trend.max_leverage,
        )
    )
    data = TrendDataLoader(cache_dir).load(SYMBOLS)
    closes = data.closes
    run = TrendPortfolio(float(TAKER_FEE)).run(
        TurnoverBuffer(trend.buffer_band).apply(signal.weights(closes)),
        closes.pct_change().shift(-1).fillna(0.0).to_numpy(),
        data.funding.shift(-1).fillna(0.0).to_numpy(),
    )
    net = pd.Series(run.net, index=closes.index + pd.Timedelta(days=1))
    return net[(net.index >= START) & (net.index < END)]


class TestTrendReplayMatchesTheVectorizedRule:
    # Gaps left: held quantities drift between rebalances while the vectorized
    # rule holds weights, lots round down, and funding settles before 00:01 trades.

    def test_daily_returns_track_the_rule(
        self, replay: ReplayResultSchema, reference: pd.Series
    ) -> None:
        daily = replay.equity.pct_change().dropna()
        both = pd.concat([daily, reference], axis=1, join="inner")

        assert len(both) == len(reference)
        assert both.corr().iloc[0, 1] > 0.95

    def test_sharpe_is_close_to_the_rule(
        self, replay: ReplayResultSchema, reference: pd.Series
    ) -> None:
        expected = TrendMetrics.sharpe(reference)

        assert expected is not None
        assert replay.stats.sharpe == pytest.approx(expected, abs=0.5)

    def test_longs_pay_positive_funding(self, replay: ReplayResultSchema) -> None:
        assert replay.funding_received < 0

    def test_every_intent_reached_the_exchange(
        self, replay: ReplayResultSchema
    ) -> None:
        assert replay.orders > 0
        assert replay.rejections == {}
        assert replay.failed_decisions == 0


async def test_rejections_are_tallied_by_reason(
    app_config: AppConfig, cache_dir: Path
) -> None:
    # 5x puts liquidation about 20% away, inside the 30% disaster stop.
    futures = app_config.futures.model_copy(update={"default_leverage": 5})
    config = app_config.model_copy(update={"futures": futures})
    data = ReplayDataLoader(cache_dir).load(NEEDS)
    composer = ReplayComposer(config, _precision(), replay_costs(TAKER_FEE, Decimal(0)))
    rig = await composer.compose("trend_following", data, _ms(START))
    end = START + pd.Timedelta(days=30)

    result = await ReplayRunner(rig, data).run(_ms(START), _ms(end))

    assert result.orders == 0
    assert list(result.rejections) == ["Stop loss at or beyond liquidation price"]
    assert result.final_equity == result.initial_equity


async def test_stop_filled_in_the_bar_is_seen_before_the_rebalance(
    config: AppConfig, tmp_path: Path
) -> None:
    # 100 calm up days, then the day's last bar drops 70%: the 30%
    # disaster stop fills inside that bar and the 00:01 rebalance flattens.
    rng = np.random.default_rng(11)
    steps = 0.002 + rng.normal(0, 0.01, 102 * 6)
    steps[100 * 6 - 1] = np.log(0.3)
    _write_cache(tmp_path, {s: 100 * np.exp(np.cumsum(steps)) for s in SYMBOLS})
    data = ReplayDataLoader(tmp_path).load(NEEDS)
    composer = ReplayComposer(config, _precision(), replay_costs(TAKER_FEE, Decimal(0)))
    start = pd.Timestamp("2021-03-01")
    rig = await composer.compose("trend_following", data, _ms(start))

    result = await ReplayRunner(rig, data).run(_ms(start), _ms(start) + 42 * 86_400_000)

    assert result.orders > 0
    assert result.failed_decisions == 0


async def test_daily_closes_hide_days_that_have_not_closed() -> None:
    days = pd.to_datetime(pd.Series([0, 1, 2]), unit="D")
    closes = HistoricalDailyCloses(pd.DataFrame({"X": [1.0, 2.0, 3.0]}, index=days))

    # At 00:00 of day 2 only days 0 and 1 are final.
    seen = await closes.closes("X", 10, now_ms=2 * 86_400_000)

    assert list(seen) == [1.0, 2.0]


async def test_runner_rejects_a_start_off_midnight(
    config: AppConfig, cache_dir: Path
) -> None:
    data = ReplayDataLoader(cache_dir).load(NEEDS)
    composer = ReplayComposer(config, _precision(), replay_costs(TAKER_FEE, Decimal(0)))
    rig = await composer.compose("trend_following", data, _ms(START))

    with pytest.raises(ValueError, match="UTC midnights"):
        await ReplayRunner(rig, data).run(_ms(START) + 1, _ms(END))
