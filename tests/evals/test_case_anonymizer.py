from decimal import Decimal

import pytest

from kavzi_trader.brain.schemas.dependencies import AnalystDependenciesSchema
from kavzi_trader.evals.anonymized_case_schema import AnonymizedCaseSchema
from kavzi_trader.evals.case_anonymizer import ANONYMOUS_SYMBOL, CaseAnonymizer
from kavzi_trader.evals.case_context_builder import CaseContextBuilder
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from tests.evals.eval_fixtures import DECISION_INDEX, HISTORY, btc_frame

_WEEK_S = 7 * 24 * 3600
_PRICE_SCALE = Decimal("3.7")
_VOLUME_SCALE = Decimal("2.1")


def _scaled(anonymized: AnonymizedCaseSchema) -> AnonymizedCaseSchema:
    candles = [
        c.model_copy(
            update={
                "open_price": c.open_price * _PRICE_SCALE,
                "high_price": c.high_price * _PRICE_SCALE,
                "low_price": c.low_price * _PRICE_SCALE,
                "close_price": c.close_price * _PRICE_SCALE,
                "volume": c.volume * _VOLUME_SCALE,
            }
        )
        for c in anonymized.candles
    ]
    return anonymized.model_copy(update={"candles": candles})


class TestWindow:
    def test_window_ends_at_decision_close_with_live_history_length(
        self, anonymizer: CaseAnonymizer, case: EvalCaseSchema
    ) -> None:
        anonymized = anonymizer.anonymize(case)

        assert len(anonymized.candles) == HISTORY
        assert anonymized.symbol == ANONYMOUS_SYMBOL
        shift_s = anonymized.time_shift_ms // 1000
        last_close_s = anonymized.candles[-1].close_time.timestamp()
        assert last_close_s - shift_s == pytest.approx(
            case.decision_close_time_ms / 1000, abs=0.01
        )

    def test_missing_decision_candle_is_an_error(
        self, anonymizer: CaseAnonymizer, case: EvalCaseSchema
    ) -> None:
        bad = case.model_copy(
            update={"decision_close_time_ms": case.decision_close_time_ms + 1}
        )

        with pytest.raises(ValueError, match="no candle closing at"):
            anonymizer.anonymize(bad)


class TestAnonymization:
    def test_no_real_symbol_date_or_price_level_in_candles(
        self, anonymizer: CaseAnonymizer, case: EvalCaseSchema
    ) -> None:
        anonymized = anonymizer.anonymize(case)

        assert {c.symbol for c in anonymized.candles} == {ANONYMOUS_SYMBOL}
        assert {c.open_time.year for c in anonymized.candles} <= {1999, 2000}
        assert anonymized.time_shift_ms % (_WEEK_S * 1000) == 0
        assert 20 <= float(anonymized.candles[-1].close_price) <= 800 * 1.5

    def test_time_of_day_survives_the_shift(
        self, anonymizer: CaseAnonymizer, case: EvalCaseSchema
    ) -> None:
        anonymized = anonymizer.anonymize(case)
        real_seconds_of_day = (case.decision_open_time_ms // 1000) % 86_400

        shifted = anonymized.candles[-1].open_time.timestamp()
        assert shifted % 86_400 == real_seconds_of_day

    def test_factors_are_deterministic_per_case(
        self, anonymizer: CaseAnonymizer, case: EvalCaseSchema
    ) -> None:
        first = anonymizer.anonymize(case)
        second = anonymizer.anonymize(case)
        other = anonymizer.anonymize(
            case.model_copy(update={"case_id": case.case_id + "-other"})
        )

        assert first.price_factor == second.price_factor
        assert first.price_factor != other.price_factor

    def test_inverse_mapping_restores_real_prices(
        self, anonymizer: CaseAnonymizer, case: EvalCaseSchema
    ) -> None:
        anonymized = anonymizer.anonymize(case)
        frame = btc_frame()
        real_close = Decimal(repr(float(frame.loc[DECISION_INDEX, "close"])))

        restored = anonymized.to_real_price(anonymized.candles[-1].close_price)

        assert restored == pytest.approx(real_close, rel=Decimal("1e-5"))
        assert float(restored) == pytest.approx(case.entry_price, rel=1e-5)


class TestScaleEquivariance:
    async def _deps(
        self,
        builder: CaseContextBuilder,
        case: EvalCaseSchema,
        anonymized: AnonymizedCaseSchema,
    ) -> AnalystDependenciesSchema:
        provider = await builder.build(case, anonymized)
        return await provider.get_analyst(anonymized.symbol)

    async def test_indicators_and_confluence_scale_with_the_inputs(
        self,
        anonymizer: CaseAnonymizer,
        context_builder: CaseContextBuilder,
        case: EvalCaseSchema,
    ) -> None:
        base = anonymizer.anonymize(case)
        a = await self._deps(context_builder, case, base)
        b = await self._deps(context_builder, case, _scaled(base))
        k = float(_PRICE_SCALE)
        ia, ib = a.indicators, b.indicators

        for name in ("ema_20", "ema_50", "ema_200", "sma_20", "atr_14"):
            assert float(getattr(ib, name)) == pytest.approx(
                k * float(getattr(ia, name)), rel=1e-4
            ), name
        assert ia.macd is not None
        assert ib.macd is not None
        assert float(ib.macd.histogram) == pytest.approx(
            k * float(ia.macd.histogram), rel=1e-3
        )
        assert ia.bollinger is not None
        assert ib.bollinger is not None
        assert float(ib.bollinger.upper) == pytest.approx(
            k * float(ia.bollinger.upper), rel=1e-4
        )
        assert float(ib.bollinger.percent_b) == pytest.approx(
            float(ia.bollinger.percent_b), abs=1e-3
        )
        assert ia.rsi_14 is not None
        assert ib.rsi_14 is not None
        assert float(ib.rsi_14) == pytest.approx(float(ia.rsi_14), abs=0.05)
        assert ia.volume is not None
        assert ib.volume is not None
        assert float(ib.volume.volume_ratio) == pytest.approx(
            float(ia.volume.volume_ratio), abs=0.05
        )
        assert b.algorithm_confluence == a.algorithm_confluence
        assert b.volatility_regime == a.volatility_regime
        assert b.htf_trend is not None
        assert a.htf_trend is not None
        assert b.htf_trend.direction == a.htf_trend.direction
