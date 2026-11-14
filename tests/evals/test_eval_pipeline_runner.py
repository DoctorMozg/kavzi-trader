from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from kavzi_trader.brain.agent.protocols import ScoutRunner
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.case_anonymizer import CaseAnonymizer
from kavzi_trader.evals.case_context_builder import CaseContextBuilder
from kavzi_trader.evals.cost_calculator import CostCalculator
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.eval_pipeline_runner import EvalPipelineRunner
from kavzi_trader.spine.filters.scout import ScoutFilter
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from tests.evals.eval_fixtures import (
    DECISION_INDEX,
    HISTORY,
    SYMBOL,
    FakeLlmAgents,
    btc_frame,
    case_at,
    write_cache,
)
from tests.evals.stub_scout import StubScout

RunnerFactory = Callable[..., EvalPipelineRunner]


@pytest.fixture
def make_runner(
    app_config: AppConfig,
    cache_dir: Path,
    context_builder: CaseContextBuilder,
) -> RunnerFactory:
    def _make(
        agents: FakeLlmAgents,
        scout: ScoutRunner,
        *,
        bypass: bool = False,
        cache: Path | None = None,
    ) -> EvalPipelineRunner:
        return EvalPipelineRunner(
            app_config,
            agents,
            scout,
            CaseAnonymizer(CandleCache(cache or cache_dir, "15m"), HISTORY),
            context_builder,
            CostCalculator(),
            bypass_scout=bypass,
        )

    return _make


@pytest.fixture
def real_scout(app_config: AppConfig) -> ScoutFilter:
    policy = RegimePolicy(app_config.risk, app_config.scout.extreme_allowed_patterns)
    return ScoutFilter(app_config.scout, policy)


class TestScoutHandling:
    async def test_skip_stops_pipeline_before_any_llm_call(
        self, make_runner: RunnerFactory, app_config: AppConfig, case: EvalCaseSchema
    ) -> None:
        agents = FakeLlmAgents(app_config)
        result = await make_runner(agents, StubScout("SKIP")).run_case(case)

        assert result.stopped_at == "scout"
        assert result.scout_verdict == "SKIP"
        assert result.analyst is None
        assert agents.calls == {"analyst": 0, "trader": 0}

    async def test_bypass_records_skip_and_continues(
        self, make_runner: RunnerFactory, app_config: AppConfig, case: EvalCaseSchema
    ) -> None:
        agents = FakeLlmAgents(app_config)
        runner = make_runner(agents, StubScout("SKIP"), bypass=True)
        result = await runner.run_case(case)

        assert result.scout_verdict == "SKIP"
        assert result.scout_bypassed
        assert agents.calls["analyst"] == 1
        assert result.analyst is not None
        assert result.analyst.direction == "LONG"

    async def test_real_scout_skips_a_quiet_regime(
        self,
        make_runner: RunnerFactory,
        app_config: AppConfig,
        real_scout: ScoutFilter,
        case: EvalCaseSchema,
    ) -> None:
        result = await make_runner(FakeLlmAgents(app_config), real_scout).run_case(case)

        assert result.rebuilt_regime == "LOW"
        assert result.scout_verdict == "SKIP"
        assert result.stopped_at == "scout"


class TestFullPipeline:
    async def test_trader_geometry_is_mapped_back_to_real_prices(
        self, make_runner: RunnerFactory, app_config: AppConfig, case: EvalCaseSchema
    ) -> None:
        agents = FakeLlmAgents(app_config)
        result = await make_runner(agents, StubScout("INTERESTING")).run_case(case)

        trader = result.trader
        assert result.stopped_at == "trader"
        assert trader is not None
        assert trader.action == "LONG"
        assert trader.entry == pytest.approx(case.entry_price, rel=1e-5)
        assert trader.entry is not None
        assert trader.stop_loss is not None
        assert trader.take_profit is not None
        assert trader.stop_loss < trader.entry < trader.take_profit
        assert trader.rr_ratio is not None
        assert trader.rr_ratio >= 2.0
        assert trader.metrics.requests == 1
        assert trader.metrics.cost_usd is None  # fake model id has no list price

    async def test_pre_trader_gate_stops_before_trader_llm(
        self, make_runner: RunnerFactory, app_config: AppConfig, tmp_path: Path
    ) -> None:
        frame = btc_frame(breakout=True)
        write_cache(tmp_path, frame)
        agents = FakeLlmAgents(app_config)
        runner = make_runner(
            agents, StubScout("INTERESTING", pattern="BREAKOUT"), cache=tmp_path
        )
        result = await runner.run_case(case_at(frame, DECISION_INDEX))

        assert result.stopped_at == "trader_gate"
        assert result.trader is not None
        assert result.trader.stop_reason == "pre_trade_gate_reject"
        assert result.trader.action == "WAIT"
        assert agents.calls["trader"] == 0
        assert result.trader.metrics.requests == 0

    async def test_analyst_refusal_is_recorded_as_no_decision(
        self, make_runner: RunnerFactory, app_config: AppConfig, case: EvalCaseSchema
    ) -> None:
        agents = FakeLlmAgents(app_config, refuse="analyst")
        result = await make_runner(agents, StubScout("INTERESTING")).run_case(case)

        assert result.status == "ok"
        assert result.stopped_at == "analyst_error"
        assert result.analyst is not None
        assert result.analyst.direction is None
        assert result.analyst.metrics.refusal
        assert result.analyst.metrics.error == "refusal"
        assert result.trader is None
        assert agents.calls["trader"] == 0

    async def test_trader_refusal_is_recorded_as_no_decision(
        self, make_runner: RunnerFactory, app_config: AppConfig, case: EvalCaseSchema
    ) -> None:
        agents = FakeLlmAgents(app_config, refuse="trader")
        result = await make_runner(agents, StubScout("INTERESTING")).run_case(case)

        assert result.stopped_at == "trader_error"
        assert result.trader is not None
        assert result.trader.stop_reason == "llm_unexpected_model"
        assert result.trader.stop_loss is None
        assert result.trader.metrics.error == "refusal"

    @pytest.mark.parametrize("role", ["analyst", "trader"])
    async def test_api_failure_marks_case_as_error_for_resume(
        self,
        make_runner: RunnerFactory,
        app_config: AppConfig,
        case: EvalCaseSchema,
        role: str,
    ) -> None:
        agents = FakeLlmAgents(app_config, http_error=role)
        result = await make_runner(agents, StubScout("INTERESTING")).run_case(case)

        assert result.stopped_at == f"{role}_error"
        assert result.status == "error"
        assert result.error is not None
        assert "ModelHTTPError" in result.error

    async def test_unparseable_trader_output_is_recorded_as_no_decision(
        self, make_runner: RunnerFactory, app_config: AppConfig, case: EvalCaseSchema
    ) -> None:
        agents = FakeLlmAgents(app_config, trader_reply={"action": "MAYBE"})
        result = await make_runner(agents, StubScout("INTERESTING")).run_case(case)

        assert result.stopped_at == "trader_error"
        assert result.trader is not None
        assert result.trader.metrics.error == "no_decision"
        assert not result.trader.metrics.refusal


class TestAnonymizationInPrompts:
    async def test_prompts_do_not_reveal_symbol_date_or_price_level(
        self, make_runner: RunnerFactory, app_config: AppConfig, case: EvalCaseSchema
    ) -> None:
        agents = FakeLlmAgents(app_config)
        await make_runner(agents, StubScout("INTERESTING")).run_case(case)

        assert agents.log.analyst
        assert agents.log.trader
        decided = datetime.fromtimestamp(case.decision_open_time_ms / 1000, tz=UTC)
        user = agents.log.user_text()
        # Instructions carry a tier legend that names BTC/ETH/BNB; only the full
        # symbol must be absent there.
        assert SYMBOL not in agents.log.all_text()
        assert "BTC" not in user
        assert "ASSET" in user
        for date_text in (
            decided.strftime("%Y-%m-%d"),
            str(decided.year),
            decided.strftime("%b"),
            decided.strftime("%A"),
        ):
            assert date_text not in agents.log.all_text()
        assert str(int(case.entry_price)) not in agents.log.all_text()
        assert f"{case.entry_price:.2f}" not in agents.log.all_text()

    async def test_tier_is_kept_for_the_llms(
        self, make_runner: RunnerFactory, app_config: AppConfig, case: EvalCaseSchema
    ) -> None:
        agents = FakeLlmAgents(app_config)
        await make_runner(agents, StubScout("INTERESTING")).run_case(case)

        assert "TIER_1" in agents.log.analyst[0]


class TestNoLookahead:
    async def _prompts(
        self,
        make_runner: RunnerFactory,
        app_config: AppConfig,
        cache: Path,
        frame: pd.DataFrame,
    ) -> FakeLlmAgents:
        write_cache(cache, frame)
        agents = FakeLlmAgents(app_config)
        runner = make_runner(agents, StubScout("INTERESTING"), cache=cache)
        await runner.run_case(case_at(frame, DECISION_INDEX))
        return agents

    async def test_candles_after_decision_do_not_change_prompts(
        self, make_runner: RunnerFactory, app_config: AppConfig, tmp_path: Path
    ) -> None:
        plain = btc_frame(extra_bars=60)
        tampered = plain.copy()
        tampered.loc[DECISION_INDEX + 1 :, ["high", "close", "volume"]] *= 5

        a = await self._prompts(make_runner, app_config, tmp_path / "a", plain)
        b = await self._prompts(make_runner, app_config, tmp_path / "b", tampered)

        assert a.log.analyst
        assert a.log.analyst == b.log.analyst
        assert a.log.trader == b.log.trader

    async def test_candles_before_decision_do_change_prompts(
        self, make_runner: RunnerFactory, app_config: AppConfig, tmp_path: Path
    ) -> None:
        plain = btc_frame()
        tampered = plain.copy()
        tampered.loc[DECISION_INDEX - 3, ["high", "close"]] *= 1.02

        a = await self._prompts(make_runner, app_config, tmp_path / "a", plain)
        b = await self._prompts(make_runner, app_config, tmp_path / "b", tampered)

        assert a.log.analyst != b.log.analyst
