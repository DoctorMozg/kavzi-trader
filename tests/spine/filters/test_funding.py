from decimal import Decimal

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
