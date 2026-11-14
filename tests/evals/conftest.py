from pathlib import Path

import pytest

from kavzi_trader.cli.composition import load_tier_registry
from kavzi_trader.config import AppConfig
from kavzi_trader.evals.candle_cache import CandleCache
from kavzi_trader.evals.case_anonymizer import CaseAnonymizer
from kavzi_trader.evals.case_context_builder import CaseContextBuilder
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from kavzi_trader.spine.risk.regime_policy import RegimePolicy
from kavzi_trader.spine.risk.volatility import VolatilityRegimeDetector
from tests.evals.eval_fixtures import (
    DECISION_INDEX,
    HISTORY,
    btc_frame,
    case_at,
    write_cache,
)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    write_cache(tmp_path / "cache", btc_frame())
    return tmp_path / "cache"


@pytest.fixture
def case() -> EvalCaseSchema:
    return case_at(btc_frame(), DECISION_INDEX)


@pytest.fixture
def anonymizer(cache_dir: Path) -> CaseAnonymizer:
    return CaseAnonymizer(CandleCache(cache_dir, "15m"), HISTORY)


@pytest.fixture
def context_builder(app_config: AppConfig) -> CaseContextBuilder:
    policy = RegimePolicy(app_config.risk, app_config.scout.extreme_allowed_patterns)
    return CaseContextBuilder(
        app_config,
        load_tier_registry(),
        VolatilityRegimeDetector(app_config.risk, policy),
    )
