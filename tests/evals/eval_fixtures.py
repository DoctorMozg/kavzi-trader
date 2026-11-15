import json
from pathlib import Path

import pandas as pd
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from kavzi_trader.brain.agent.factory import AgentFactory
from kavzi_trader.brain.config import BrainConfigSchema
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.brain.schemas.dependencies import (
    AnalystDependenciesSchema,
    TradingDependenciesSchema,
)
from kavzi_trader.cli.composition import load_tier_registry
from kavzi_trader.config import AppConfig
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.domain.trade_decision import TradeDecisionSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from tests.evals.frames import make_frame

SYMBOL = "BTCUSDT"
HISTORY = 1000
PRICE_SCALE = 960.0
DECISION_INDEX = HISTORY + 99
ANALYST_JSON = {
    "setup_valid": True,
    "direction": "LONG",
    "confluence_score": 11,
    "key_levels": {"levels": []},
    "reasoning": "Synthetic analyst verdict used by the eval runner tests, long.",
}
TRADER_JSON = {
    "action": "LONG",
    "confidence": 0.8,
    "reasoning": "Synthetic trader verdict used by the eval runner tests, long.",
    "entry_tactic": "IMMEDIATE",
    "stop_atr_multiplier": 1.5,
    "target_style": "ATR_2X",
}


def btc_frame(
    extra_bars: int = 0, seed: int = 3, *, breakout: bool = False
) -> pd.DataFrame:
    """~96k-priced candles; the decision candle is DECISION_INDEX, on a volume spike."""
    frame = make_frame(HISTORY + 100 + extra_bars, seed=seed, drift_vol=0.003)
    frame.loc[DECISION_INDEX, "volume"] = 40.0
    for column in ("open", "high", "low", "close"):
        frame[column] = frame[column] * PRICE_SCALE
    if breakout:
        # Close far above the Bollinger band so the BREAKOUT %B gate trips.
        spike = frame.loc[DECISION_INDEX - 1, "close"] * 1.08
        frame.loc[DECISION_INDEX, ["high", "close"]] = spike
    return frame


def write_cache(
    cache_dir: Path, frame: pd.DataFrame, symbol: str = SYMBOL, interval: str = "15m"
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{symbol}_{interval}.csv.gz"
    frame.to_csv(path, index=False, compression="gzip")


def case_at(frame: pd.DataFrame, index: int, **overrides: object) -> EvalCaseSchema:
    row = frame.iloc[index]
    side = {"outcome": "tp", "bars_to_exit": 5, "r_multiple": 2.0}
    data: dict[str, object] = {
        "case_id": f"{SYMBOL}-{int(row['close_time_ms'])}",
        "symbol": SYMBOL,
        "decision_open_time_ms": int(row["open_time_ms"]),
        "decision_close_time_ms": int(row["close_time_ms"]),
        "interval": "15m",
        "regime": "NORMAL",
        "atr_zscore": 0.1,
        "tier": "TIER_1",
        "entry_price": float(row["close"]),
        "atr_14": 100.0,
        "label": "LONG",
        "long": side,
        "short": {**side, "outcome": "sl", "r_multiple": -1.0},
        "sl_atr_multiple": 1.25,
        "tp_atr_multiple": 2.5,
        "dataset_version": "v1",
        "seed": 1,
        "generator": json.loads(_GENERATOR),
    }
    return EvalCaseSchema.model_validate(data | overrides)


_GENERATOR = json.dumps(
    {
        "months": 1.0,
        "cases": 1,
        "symbols": [SYMBOL],
        "interval": "15m",
        "history_candles": HISTORY,
        "horizon_bars": 96,
        "min_spacing_bars": 96,
        "window_start_ms": 0,
        "data_end_ms": 0,
        "stop_atr_by_regime": {
            "LOW": 1.25,
            "NORMAL": 1.25,
            "HIGH": 1.5,
            "EXTREME": 1.5,
        },
        "tp_style": "ATR_2X",
        "min_rr_ratio": 2.0,
    }
)


class PromptLog:
    """What the fake models were asked: user prompts per agent, plus instructions."""

    def __init__(self) -> None:
        self.analyst: list[str] = []
        self.trader: list[str] = []
        self.instructions: list[str] = []

    def user_text(self) -> str:
        return "\n".join(self.analyst + self.trader)

    def all_text(self) -> str:
        return "\n".join([*self.instructions, self.user_text()])


def _user_text(messages: list[ModelMessage]) -> str:
    return "\n".join(
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if hasattr(part, "content")
    )


def _instructions(messages: list[ModelMessage]) -> list[str]:
    return [
        message.instructions
        for message in messages
        if isinstance(message, ModelRequest) and message.instructions
    ]


class FakeLlmAgents:
    """Real AgentFactory agents (real prompts, schemas) on scripted FunctionModels."""

    def __init__(
        self,
        app_config: AppConfig,
        analyst_reply: dict[str, object] | None = None,
        trader_reply: dict[str, object] | None = None,
        *,
        refuse: str | None = None,
        http_error: str | None = None,
    ) -> None:
        brain = BrainConfigSchema.model_validate(
            {
                "analyst": {"provider": "anthropic"},
                "trader": {"provider": "anthropic"},
                "anthropic_api_key": "test-key",
            }
        )
        self._factory = AgentFactory(
            brain,
            PromptLoader(),
            risk_config=app_config.risk,
            tier_registry=load_tier_registry(),
        )
        self._replies = {
            "analyst": ANALYST_JSON | (analyst_reply or {}),
            "trader": TRADER_JSON | (trader_reply or {}),
        }
        self._refuse = refuse
        self._http_error = http_error
        self.log = PromptLog()
        self.calls = {"analyst": 0, "trader": 0}

    def _model(self, role: str) -> FunctionModel:
        sink = self.log.analyst if role == "analyst" else self.log.trader

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            sink.append(_user_text(messages))
            self.log.instructions.extend(_instructions(messages))
            self.calls[role] += 1
            if self._http_error == role:
                raise ModelHTTPError(400, f"fake-{role}", {"error": "bad request"})
            if self._refuse == role:
                return ModelResponse(parts=[], finish_reason="content_filter")
            return ModelResponse(parts=[TextPart(json.dumps(self._replies[role]))])

        return FunctionModel(respond, model_name=f"fake-{role}")

    def create_analyst_agent(
        self,
    ) -> Agent[AnalystDependenciesSchema, AnalystDecisionSchema]:
        agent = self._factory.create_analyst_agent()
        agent.model = self._model("analyst")
        return agent

    def create_trader_agent(
        self,
    ) -> Agent[TradingDependenciesSchema, TradeDecisionSchema]:
        agent = self._factory.create_trader_agent()
        agent.model = self._model("trader")
        return agent
