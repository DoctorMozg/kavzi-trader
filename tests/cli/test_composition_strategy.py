from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from kavzi_trader.cli.composition import OrchestratorComposer
from kavzi_trader.config import AppConfig
from kavzi_trader.orchestrator.loops.llm_pipeline_plugin import LlmPipelinePlugin
from kavzi_trader.paper.mode import TradingMode
from kavzi_trader.strategies.strategy_config import StrategyConfigSchema
from kavzi_trader.strategies.trend.trend_following_plugin import TrendFollowingPlugin


def _config(
    base: AppConfig,
    active: str = "trend_following",
    mode: TradingMode = TradingMode.PAPER,
    reset_on_start: bool = False,
    balance: str = "10000",
) -> AppConfig:
    return base.model_copy(
        update={
            "strategy": StrategyConfigSchema(active=active),  # type: ignore[arg-type]
            "paper": base.paper.model_copy(
                update={
                    "mode": mode,
                    "reset_on_start": reset_on_start,
                    "initial_balance_usdt": Decimal(balance),
                }
            ),
        }
    )


class TestTrendFollowingGuards:
    async def test_live_mode_is_refused(self, app_config: AppConfig) -> None:
        composer = OrchestratorComposer(
            _config(app_config, mode=TradingMode.LIVE), paper=True
        )

        with pytest.raises(ValueError, match="paper-only"):
            await composer.compose()

    async def test_start_without_paper_flag_is_refused(
        self, app_config: AppConfig
    ) -> None:
        composer = OrchestratorComposer(_config(app_config), paper=False)

        with pytest.raises(ValueError, match="paper-only"):
            await composer.compose()

    async def test_reset_on_start_is_refused(self, app_config: AppConfig) -> None:
        composer = OrchestratorComposer(
            _config(app_config, reset_on_start=True), paper=True
        )

        with pytest.raises(ValueError, match="reset_on_start"):
            await composer.compose()

    def test_small_balance_warns(
        self, app_config: AppConfig, caplog: pytest.LogCaptureFixture
    ) -> None:
        composer = OrchestratorComposer(_config(app_config, balance="100"), paper=True)

        with caplog.at_level("WARNING"):
            composer._validate_strategy()

        assert "below min notional" in caplog.text

    def test_default_balance_does_not_warn(
        self, app_config: AppConfig, caplog: pytest.LogCaptureFixture
    ) -> None:
        composer = OrchestratorComposer(_config(app_config), paper=True)

        with caplog.at_level("WARNING"):
            composer._validate_strategy()

        assert "below min notional" not in caplog.text


class TestStrategySelection:
    def test_trend_following_builds_the_trend_plugin(
        self, app_config: AppConfig
    ) -> None:
        composer = OrchestratorComposer(_config(app_config), paper=True)

        wiring = composer._create_strategy_wiring(MagicMock(), MagicMock(), MagicMock())

        assert isinstance(wiring.loop._plugin, TrendFollowingPlugin)
        assert wiring.external_loop is None

    def test_shipped_config_runs_trend_and_passes_its_guards(
        self, app_config: AppConfig
    ) -> None:
        composer = OrchestratorComposer(app_config, paper=True)

        composer._validate_strategy()

        assert app_config.strategy.active == "trend_following"

    def test_llm_pipeline_builds_the_llm_plugin(self, app_config: AppConfig) -> None:
        configured = _config(app_config, active="llm_pipeline")
        base = configured.model_copy(
            update={
                "brain": configured.brain.model_copy(
                    update={"openrouter_api_key": SecretStr("test")}
                )
            }
        )
        composer = OrchestratorComposer(base, paper=True)

        wiring = composer._create_strategy_wiring(MagicMock(), MagicMock(), MagicMock())

        assert isinstance(wiring.loop._plugin, LlmPipelinePlugin)
