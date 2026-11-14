from decimal import Decimal
from typing import Literal

import pytest

from kavzi_trader.order_flow.schemas import OrderFlowSchema
from kavzi_trader.spine.filters.config import FilterConfigSchema
from kavzi_trader.spine.filters.funding import FundingRateFilter


def test_funding_blocks_crowded_long(sample_order_flow) -> None:
    config = FilterConfigSchema()
    funding_filter = FundingRateFilter(config)
    crowded = sample_order_flow.model_copy(
        update={"funding_zscore": Decimal("3.0")},
    )

    result = funding_filter.evaluate(side="LONG", order_flow=crowded)

    assert result.is_allowed is False, "Expected crowded long to be blocked"


def test_funding_blocks_crowded_short(sample_order_flow) -> None:
    config = FilterConfigSchema()
    funding_filter = FundingRateFilter(config)
    crowded = sample_order_flow.model_copy(
        update={"funding_zscore": Decimal("-3.0")},
    )

    result = funding_filter.evaluate(side="SHORT", order_flow=crowded)

    assert result.is_allowed is False, "Expected crowded short to be blocked"


def test_funding_allows_neutral(sample_order_flow) -> None:
    config = FilterConfigSchema()
    funding_filter = FundingRateFilter(config)

    result = funding_filter.evaluate(side="LONG", order_flow=sample_order_flow)

    assert result.is_allowed is True, "Expected neutral funding to allow"


def _multiplier(
    funding_filter: FundingRateFilter,
    order_flow: OrderFlowSchema,
    side: Literal["LONG", "SHORT"],
    zscore: str,
    symbol: str | None = None,
) -> Decimal:
    flow = order_flow.model_copy(update={"funding_zscore": Decimal(zscore)})
    result = funding_filter.evaluate(side=side, order_flow=flow, symbol=symbol)
    return result.size_multiplier if result.is_allowed else Decimal(0)


def test_funding_reduces_size_on_moderate_adverse_long(sample_order_flow) -> None:
    funding_filter = FundingRateFilter(FilterConfigSchema())

    assert _multiplier(funding_filter, sample_order_flow, "LONG", "1.5") == Decimal(
        "0.8",
    )


def test_funding_reduces_size_on_moderate_adverse_short(sample_order_flow) -> None:
    funding_filter = FundingRateFilter(FilterConfigSchema())

    assert _multiplier(funding_filter, sample_order_flow, "SHORT", "-1.5") == Decimal(
        "0.8",
    )


def test_funding_keeps_full_size_below_lower_bound(sample_order_flow) -> None:
    funding_filter = FundingRateFilter(FilterConfigSchema())

    assert _multiplier(funding_filter, sample_order_flow, "LONG", "0.9") == 1


def test_funding_keeps_full_size_when_favourable(sample_order_flow) -> None:
    funding_filter = FundingRateFilter(FilterConfigSchema())

    assert _multiplier(funding_filter, sample_order_flow, "SHORT", "1.5") == 1


def test_funding_band_follows_custom_lower_and_multiplier(sample_order_flow) -> None:
    config = FilterConfigSchema(
        funding_reduce_zscore_lower=Decimal("0.5"),
        funding_reduce_size_multiplier=Decimal("0.6"),
    )
    funding_filter = FundingRateFilter(config)

    assert _multiplier(funding_filter, sample_order_flow, "LONG", "0.5") == Decimal(
        "0.6",
    )


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize("crowded", ["2.0", "2.5", "3.0"])
def test_funding_size_never_increases_as_adverse_zscore_grows(
    sample_order_flow,
    make_tier_registry,
    side,
    crowded,
) -> None:
    """Regression: z=2.2 on a 2.5 tier used to get 1.0 while z=1.5 got 0.8."""
    funding_filter = FundingRateFilter(
        FilterConfigSchema(), make_tier_registry(crowded)
    )
    sign = 1 if side == "LONG" else -1
    zscores = [Decimal(i) / 10 for i in range(41)]

    multipliers = [
        _multiplier(funding_filter, sample_order_flow, side, str(sign * z), "SOLUSDT")
        for z in zscores
    ]

    assert multipliers == sorted(multipliers, reverse=True)
    assert Decimal("0.8") in multipliers
    assert multipliers[-1] == 0, "Expected a block beyond the crowded threshold"
