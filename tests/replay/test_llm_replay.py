from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import pytest_asyncio

from kavzi_trader.cli.replay_composition import (
    ReplayComposer,
    replay_costs,
    replay_needs,
)
from kavzi_trader.config import AppConfig
from kavzi_trader.domain.symbol_filters import SymbolFiltersSchema
from kavzi_trader.evals.archive_series import ArchiveSeries
from kavzi_trader.evals.candle_cache import COLUMNS
from kavzi_trader.evals.metrics_cache import (
    GLOBAL_RATIO,
    OPEN_INTEREST,
    TIME,
    TOP_POSITION_RATIO,
)
from kavzi_trader.events.event_schema import EventSchema
from kavzi_trader.replay.llm_tape import LlmTape
from kavzi_trader.replay.replay_data_loader import ReplayDataLoader
from kavzi_trader.replay.replay_result_schema import ReplayResultSchema
from kavzi_trader.replay.replay_runner import ReplayRunner
from kavzi_trader.replay.taped_agent_source import TapedAgentSource
from kavzi_trader.replay.training_cutoff import is_contaminated
from kavzi_trader.spine.precision.symbol_precision import SymbolPrecision
from tests.archive.conftest import write_bars, write_funding, write_metrics
from tests.evals.eval_fixtures import FakeLlmAgents

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
FIRST_BAR_MS = 1_609_459_200_000  # 2021-01-01
BAR_MS = 15 * 60_000
DAYS = 20
START = pd.Timestamp("2021-01-14")
END = pd.Timestamp("2021-01-21")

pytestmark = pytest.mark.asyncio(loop_scope="module")


class ReplayRun:
    """One llm_pipeline replay over the synthetic archive, with its decision log."""

    def __init__(self, result: ReplayResultSchema, events: list[EventSchema]) -> None:
        self.result = result
        self.events = events

    def decisions(self) -> list[tuple[str, str, str]]:
        # Event ids and decision ids are fresh UUIDs on every run.
        return [
            (e.event_type, str(e.data.get("symbol")), str(e.data.get("reason")))
            for e in self.events
        ]


def _write_archive(root: Path) -> None:
    rng = np.random.default_rng(5)
    n_bars = DAYS * 96
    open_ms = FIRST_BAR_MS + np.arange(n_bars) * BAR_MS
    for i, symbol in enumerate(SYMBOLS):
        drift = np.where((np.arange(n_bars) // 200) % 2 == 0, 0.0012, -0.0010)
        walk = np.exp(np.cumsum(drift + rng.normal(0, 0.004, n_bars)))
        # Real closes sit on the tick grid; off-grid ones make entries rest.
        close = np.round(100 * (i + 1) * walk, 2)
        open_ = np.concatenate([[close[0]], close[:-1]])
        volume = rng.lognormal(4, 0.5, n_bars)
        bars = pd.DataFrame(
            {
                "open_time_ms": open_ms,
                "open": open_,
                "high": np.round(np.maximum(open_, close) * 1.002, 2),
                "low": np.round(np.minimum(open_, close) * 0.998, 2),
                "close": close,
                "volume": volume,
                "close_time_ms": open_ms + BAR_MS - 1,
                "quote_volume": volume * close,
                "trades_count": 100,
                "taker_buy_base_volume": volume / 2,
                "taker_buy_quote_volume": volume * close / 2,
            },
            columns=list(COLUMNS),
        )
        write_bars(root, symbol, bars, BAR_MS)
        settle_ms = FIRST_BAR_MS + np.arange(DAYS * 3) * 8 * 3_600_000
        write_funding(root, symbol, settle_ms.tolist(), 0.0001)
        snaps = FIRST_BAR_MS + np.arange(DAYS * 288) * 300_000
        write_metrics(
            root,
            symbol,
            pd.DataFrame(
                {
                    TIME: snaps,
                    OPEN_INTEREST: 1e6 + 10 * np.arange(len(snaps)),
                    GLOBAL_RATIO: 1.2,
                    TOP_POSITION_RATIO: 1.1,
                }
            ),
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
    trading = app_config.trading.model_copy(update={"symbols": SYMBOLS})
    return app_config.model_copy(update={"trading": trading})


@pytest.fixture(scope="module")
def archive(tmp_path_factory: pytest.TempPathFactory) -> ArchiveSeries:
    path = tmp_path_factory.mktemp("llm_replay_archive")
    _write_archive(path)
    return ArchiveSeries(path)


@pytest.fixture(scope="module")
def tape_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("tape") / "tape.jsonl"


async def _run(
    config: AppConfig, archive: ArchiveSeries, agents: TapedAgentSource
) -> ReplayRun:
    data = ReplayDataLoader(archive).load(replay_needs(config, "llm_pipeline"))
    costs = replay_costs(Decimal("0.0005"), Decimal(0))
    composer = ReplayComposer(config, _precision(), costs, agents)
    rig = await composer.compose("llm_pipeline", data, _ms(START))
    result = await ReplayRunner(rig, data).run(_ms(START), _ms(END))
    return ReplayRun(result, await rig.event_store.read(rig.decision_stream))


@pytest.fixture(scope="module")
def fake(config: AppConfig) -> FakeLlmAgents:
    return FakeLlmAgents(config)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def recorded(
    config: AppConfig, archive: ArchiveSeries, tape_path: Path, fake: FakeLlmAgents
) -> ReplayRun:
    agents = TapedAgentSource(fake, LlmTape(tape_path), record=True)
    return await _run(config, archive, agents)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def replayed(
    config: AppConfig,
    archive: ArchiveSeries,
    tape_path: Path,
    fake: FakeLlmAgents,
    recorded: ReplayRun,
) -> ReplayRun:
    agents = TapedAgentSource(fake, LlmTape(tape_path), record=False)
    return await _run(config, archive, agents)


class TestTapedReplayIsDeterministic:
    async def test_recording_asks_the_model(
        self, recorded: ReplayRun, fake: FakeLlmAgents
    ) -> None:
        llm = recorded.result.llm

        assert llm is not None
        assert llm.provider_calls > 0
        assert llm.tape_misses == 0
        assert recorded.result.orders > 0

    async def test_entries_fill_and_move_equity(self, recorded: ReplayRun) -> None:
        assert recorded.result.final_equity != recorded.result.initial_equity
        assert recorded.result.failed_decisions == 0

    async def test_second_run_makes_no_provider_calls(
        self, recorded: ReplayRun, replayed: ReplayRun, fake: FakeLlmAgents
    ) -> None:
        llm = replayed.result.llm

        assert llm is not None
        assert llm.provider_calls == 0
        assert llm.tape_misses == 0
        assert sum(fake.calls.values()) == recorded.result.llm.provider_calls  # type: ignore[union-attr]

    async def test_second_run_makes_the_same_decisions(
        self, recorded: ReplayRun, replayed: ReplayRun
    ) -> None:
        assert replayed.decisions() == recorded.decisions()
        assert replayed.result.final_equity == recorded.result.final_equity

    async def test_fake_models_have_no_known_cutoff(self, recorded: ReplayRun) -> None:
        assert recorded.result.llm is not None
        assert recorded.result.llm.contaminated


async def test_replay_only_run_counts_requests_missing_from_the_tape(
    config: AppConfig, archive: ArchiveSeries, tmp_path: Path, fake: FakeLlmAgents
) -> None:
    calls_before = sum(fake.calls.values())
    agents = TapedAgentSource(fake, LlmTape(tmp_path / "empty.jsonl"), record=False)

    run = await _run(config, archive, agents)

    assert run.result.llm is not None
    assert run.result.llm.tape_misses > 0
    assert run.result.orders == 0
    assert sum(fake.calls.values()) == calls_before


@pytest.mark.parametrize(
    ("models", "start", "contaminated"),
    [
        (["claude-opus-5-5", "claude-sonnet-5-5"], "2026-07-01", False),
        (["claude-opus-5-5"], "2026-06-30", True),
        (["anthropic/claude-sonnet-5-5"], "2026-09-01", False),
        (["claude-sonnet-5-5", "some-other-model"], "2026-09-01", True),
    ],
)
def test_window_is_contaminated_before_any_models_cutoff(
    models: list[str], start: str, contaminated: bool
) -> None:
    assert is_contaminated(models, _ms(pd.Timestamp(start))) is contaminated
