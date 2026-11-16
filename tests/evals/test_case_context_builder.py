from decimal import Decimal

from kavzi_trader.cli.composition import load_tier_registry
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.case_anonymizer import CaseAnonymizer
from kavzi_trader.evals.case_context_builder import CaseContextBuilder
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.evals.synthetic_account import EVAL_BALANCE_USDT
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector


async def test_account_balance_ignores_paper_config(
    app_config: AppConfig, anonymizer: CaseAnonymizer, case: EvalCaseSchema
) -> None:
    paper = app_config.paper.model_copy(update={"initial_balance_usdt": Decimal(10000)})
    config = app_config.model_copy(update={"paper": paper})
    policy = RegimePolicy(config.risk, config.scout.extreme_allowed_patterns)
    builder = CaseContextBuilder(
        config, load_tier_registry(), VolatilityRegimeDetector(config.risk, policy)
    )
    anonymized = anonymizer.anonymize(case)

    provider = await builder.build(case, anonymized)
    deps = await provider.get_trader(anonymized.symbol)

    assert deps.account_state.total_balance_usdt == EVAL_BALANCE_USDT == Decimal(100)
