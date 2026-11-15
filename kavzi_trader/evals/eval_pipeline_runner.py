import logging
from decimal import Decimal

from pydantic_ai.models import Model

from kavzi_trader.brain.agent.analyst import AnalystAgent
from kavzi_trader.brain.agent.analyst_pipeline import analyst_gates
from kavzi_trader.brain.agent.protocols import ScoutRunner
from kavzi_trader.brain.agent.router import (
    ANALYST_MIN_ALGO_CONFLUENCE,
    AgentRouter,
    PipelineResult,
)
from kavzi_trader.brain.agent.trader import TraderAgent
from kavzi_trader.brain.context.builder import ContextBuilder
from kavzi_trader.brain.geometry.calculator import TradeGeometryCalculator
from kavzi_trader.brain.prompts.loader import PromptLoader
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.agent_source import AgentSource
from kavzi_trader.evals.analyst_record_schema import AnalystRecordSchema
from kavzi_trader.evals.anonymized_case_schema import AnonymizedCaseSchema
from kavzi_trader.evals.case_anonymizer import CaseAnonymizer
from kavzi_trader.evals.case_context_builder import CaseContextBuilder
from kavzi_trader.evals.case_meter import CaseMeter
from kavzi_trader.evals.case_result_schema import CaseResultSchema, StopStage
from kavzi_trader.evals.cost_calculator import CostCalculator
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.metered_model import MeteredModel
from kavzi_trader.evals.recording_scout import RecordingScout
from kavzi_trader.evals.stage_metrics_schema import StageMetricsSchema
from kavzi_trader.evals.trader_record_schema import TraderRecordSchema

logger = logging.getLogger(__name__)

_REASONING_CHARS = 1000
_TRADER_ERROR_REASONS = frozenset({"llm_timeout", "llm_unexpected_model", "llm_error"})


class EvalPipelineRunner:
    """Runs one case through the live AgentRouter on rebuilt, anonymized inputs."""

    def __init__(
        self,
        app_config: AppConfig,
        agents: AgentSource,
        scout: ScoutRunner,
        anonymizer: CaseAnonymizer,
        contexts: CaseContextBuilder,
        costs: CostCalculator,
        *,
        bypass_scout: bool,
        force_trader: bool = False,
    ) -> None:
        self._config = app_config
        self._scout = scout
        self._anonymizer = anonymizer
        self._contexts = contexts
        self._costs = costs
        self._bypass_scout = bypass_scout
        self._force_trader = force_trader
        loader = PromptLoader()
        analyst_agent = agents.create_analyst_agent()
        trader_agent = agents.create_trader_agent()
        analyst_model = _llm(analyst_agent.model)
        trader_model = _llm(trader_agent.model)
        self._analyst_model = analyst_model.model_name
        self._trader_model = trader_model.model_name
        analyst_agent.model = MeteredModel(analyst_model, "analyst")
        trader_agent.model = MeteredModel(trader_model, "trader")
        builder = ContextBuilder()
        self._analyst = AnalystAgent(analyst_agent, loader, builder)
        self._trader = TraderAgent(trader_agent, loader, builder)

    async def run_case(self, case: EvalCaseSchema) -> CaseResultSchema:
        anonymized = self._anonymizer.anonymize(case)
        provider = await self._contexts.build(case, anonymized)
        scout = RecordingScout(self._scout, bypass=self._bypass_scout)
        # A fresh router per case keeps dedup caches and circuits from leaking.
        router = AgentRouter(
            scout,
            self._analyst,
            self._trader,
            geometry_calculator=TradeGeometryCalculator(self._config.risk),
            analyst_concurrency_limit=self._config.brain.analyst_concurrency_limit,
        )
        meter = CaseMeter()
        with meter:
            result = await router.run(anonymized.symbol, provider)
            stopped_at = self._live_stop(result, meter)
            forced = self._force_trader and stopped_at == "analyst_gate"
            if forced:
                logger.info(
                    "Forcing the Trader on %s past the Analyst gate", case.case_id
                )
                result = await router.run_trader_stage(
                    anonymized.symbol, result, provider
                )
        return self._record(case, anonymized, scout, result, meter, stopped_at, forced)

    async def reaches_analyst_llm(self, case: EvalCaseSchema) -> bool:
        """Whether Scout and the algo-confluence pre-filter let the case reach the
        Analyst LLM. Runs no LLM call."""
        anonymized = self._anonymizer.anonymize(case)
        provider = await self._contexts.build(case, anonymized)
        scout = RecordingScout(self._scout, bypass=self._bypass_scout)
        scout_deps = await provider.get_scout(anonymized.symbol)
        if not scout_deps.recent_candles:
            return False
        if (await scout.run(scout_deps)).verdict != "INTERESTING":
            return False
        deps = await provider.get_analyst(anonymized.symbol)
        confluence = deps.algorithm_confluence
        min_algo = analyst_gates(deps).adjusted(ANALYST_MIN_ALGO_CONFLUENCE)
        return max(confluence.long.score, confluence.short.score) >= min_algo

    def _live_stop(self, result: PipelineResult, meter: CaseMeter) -> StopStage:
        return self._stopped_at(
            result,
            meter.metrics("analyst", self._analyst_model, self._costs),
            meter.metrics("trader", self._trader_model, self._costs),
        )

    def _record(
        self,
        case: EvalCaseSchema,
        anonymized: AnonymizedCaseSchema,
        scout: RecordingScout,
        result: PipelineResult,
        meter: CaseMeter,
        stopped_at: StopStage,
        forced: bool,
    ) -> CaseResultSchema:
        analyst_metrics = meter.metrics("analyst", self._analyst_model, self._costs)
        trader_metrics = meter.metrics("trader", self._trader_model, self._costs)
        real_scout = scout.verdict
        # A failed API request is infrastructure, not a decision: mark it so
        # --resume retries the case instead of scoring it as "no trade".
        api_error = {
            "analyst_error": analyst_metrics.error,
            "trader_error": trader_metrics.error,
        }.get(stopped_at) or (trader_metrics.error if forced else None)
        return CaseResultSchema(
            case_id=case.case_id,
            status="error" if api_error else "ok",
            error=api_error,
            label=case.label.value,
            regime=case.regime,
            tier=case.tier,
            rebuilt_regime=scout.regime.value if scout.regime else None,
            scout_verdict=real_scout.verdict if real_scout else None,
            scout_reason=real_scout.reason if real_scout else None,
            scout_pattern=real_scout.pattern_detected if real_scout else None,
            scout_bypassed=(
                self._bypass_scout
                and real_scout is not None
                and real_scout.verdict != "INTERESTING"
            ),
            stopped_at=stopped_at,
            trader_forced=forced,
            analyst=self._analyst_record(result, analyst_metrics),
            trader=self._trader_record(anonymized, result, trader_metrics),
        )

    @classmethod
    def _stopped_at(
        cls,
        result: PipelineResult,
        analyst_metrics: StageMetricsSchema,
        trader_metrics: StageMetricsSchema,
    ) -> StopStage:
        if result.scout.verdict != "INTERESTING":
            return "scout"
        if result.analyst is None:
            return "analyst_error"
        if analyst_metrics.requests == 0:
            return "analyst_skipped"
        if result.trader is None:
            return "trader_error" if trader_metrics.requests else "analyst_gate"
        return cls._trader_stage(result.trader_stop_reason)

    @staticmethod
    def _trader_stage(stop_reason: str | None) -> StopStage:
        if stop_reason == "pre_trade_gate_reject":
            return "trader_gate"
        if stop_reason in _TRADER_ERROR_REASONS:
            return "trader_error"
        return "trader"

    @staticmethod
    def _analyst_record(
        result: PipelineResult, metrics: StageMetricsSchema
    ) -> AnalystRecordSchema | None:
        decision = result.analyst
        if decision is None:
            return (
                AnalystRecordSchema(metrics=_with_failure(metrics))
                if metrics.requests
                else None
            )
        return AnalystRecordSchema(
            setup_valid=decision.setup_valid,
            direction=decision.direction,
            confluence_score=decision.confluence_score,
            reasoning=decision.reasoning[:_REASONING_CHARS],
            metrics=metrics,
        )

    @staticmethod
    def _trader_record(
        anonymized: AnonymizedCaseSchema,
        result: PipelineResult,
        metrics: StageMetricsSchema,
    ) -> TraderRecordSchema | None:
        decision = result.trader
        if decision is None:
            return (
                TraderRecordSchema(
                    stop_reason="llm_error", metrics=_with_failure(metrics)
                )
                if metrics.requests
                else None
            )
        geometry = result.geometry
        failed = result.trader_stop_reason in _TRADER_ERROR_REASONS
        return TraderRecordSchema(
            action=decision.action,
            confidence=decision.confidence,
            entry=_real(anonymized, geometry.entry) if geometry else None,
            stop_loss=_real(anonymized, geometry.stop_loss) if geometry else None,
            take_profit=_real(anonymized, geometry.take_profit) if geometry else None,
            rr_ratio=float(geometry.rr_ratio) if geometry else None,
            stop_reason=result.trader_stop_reason,
            reasoning=decision.reasoning[:_REASONING_CHARS],
            metrics=_with_failure(metrics) if failed else metrics,
        )


def _llm(model: Model | str | None) -> Model:
    if not isinstance(model, Model):
        msg = f"Agent model must be a Model instance, got {model!r}"
        raise TypeError(msg)
    return model


def _real(anonymized: AnonymizedCaseSchema, price: Decimal) -> float:
    return float(anonymized.to_real_price(price))


def _with_failure(metrics: StageMetricsSchema) -> StageMetricsSchema:
    """Mark a stage that produced no usable decision, unless it has a cause."""
    if metrics.error:
        return metrics
    return metrics.model_copy(
        update={"error": "refusal" if metrics.refusal else "no_decision"}
    )
