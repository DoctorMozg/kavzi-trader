from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from kavzi_trader.spine.risk.liquidation_calculator import LiquidationCalculator


def _bracket_payload() -> list[dict[str, object]]:
    return [
        {
            "symbol": "BTCUSDT",
            "brackets": [
                {
                    "bracket": 1,
                    "initialLeverage": 125,
                    "notionalFloor": 0,
                    "notionalCap": 50000,
                    "maintMarginRatio": 0.004,
                    "cum": 0.0,
                },
                {
                    "bracket": 2,
                    "initialLeverage": 100,
                    "notionalFloor": 50000,
                    "notionalCap": 250000,
                    "maintMarginRatio": 0.005,
                    "cum": 50.0,
                },
                {
                    "bracket": 3,
                    "initialLeverage": 50,
                    "notionalFloor": 250000,
                    "notionalCap": 1000000,
                    "maintMarginRatio": 0.01,
                    "cum": 1300.0,
                },
            ],
        },
    ]


@pytest.fixture
def mock_exchange() -> MagicMock:
    exchange = MagicMock()
    exchange.futures_get_leverage_brackets = AsyncMock(
        return_value=_bracket_payload(),
    )
    return exchange


class TestLiquidationCalculator:
    @pytest.mark.asyncio
    async def test_selects_first_bracket_for_small_notional(
        self, mock_exchange
    ) -> None:
        calc = LiquidationCalculator(mock_exchange)

        liq = await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(10000),
        )

        # WB=1000, q=0.2, cum=0: (1000 - 10000) / (0.2 * (0.004 - 1))
        assert liq == pytest.approx(Decimal("45180.7228915663"), abs=Decimal("1e-6"))

    @pytest.mark.asyncio
    async def test_selects_middle_bracket_for_mid_notional(self, mock_exchange) -> None:
        calc = LiquidationCalculator(mock_exchange)

        liq = await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(100000),
        )

        # WB=10000, q=2, cum=50: (10000 + 50 - 100000) / (2 * (0.005 - 1))
        assert liq == pytest.approx(Decimal("45201.0050251256"), abs=Decimal("1e-6"))

    @pytest.mark.asyncio
    async def test_computes_short_liquidation_correctly(self, mock_exchange) -> None:
        calc = LiquidationCalculator(mock_exchange)

        liq = await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="SHORT",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(10000),
        )

        # WB=1000, q=0.2, cum=0: (1000 + 10000) / (0.2 * (0.004 + 1))
        assert liq == pytest.approx(Decimal("54780.8764940239"), abs=Decimal("1e-6"))

    @pytest.mark.asyncio
    async def test_short_in_second_bracket_uses_maintenance_amount(
        self, mock_exchange
    ) -> None:
        calc = LiquidationCalculator(mock_exchange)

        liq = await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="SHORT",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(100000),
        )

        # WB=10000, q=2, cum=50: (10000 + 50 + 100000) / (2 * (0.005 + 1))
        assert liq == pytest.approx(Decimal("54751.2437810945"), abs=Decimal("1e-6"))

    @pytest.mark.asyncio
    async def test_returns_none_on_api_failure(self, mock_exchange) -> None:
        mock_exchange.futures_get_leverage_brackets = AsyncMock(
            side_effect=RuntimeError("network down"),
        )
        calc = LiquidationCalculator(mock_exchange)

        result = await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(10000),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_brackets(self, mock_exchange) -> None:
        mock_exchange.futures_get_leverage_brackets = AsyncMock(return_value=[])
        calc = LiquidationCalculator(mock_exchange)

        result = await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(10000),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_caches_bracket_data_across_calls(self, mock_exchange) -> None:
        calc = LiquidationCalculator(mock_exchange)

        await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(10000),
        )
        await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="SHORT",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(10000),
        )

        assert mock_exchange.futures_get_leverage_brackets.call_count == 1

    @pytest.mark.asyncio
    async def test_caches_per_symbol(self, mock_exchange) -> None:
        def _response(symbol: str) -> list[dict[str, object]]:
            return [
                {
                    "symbol": symbol,
                    "brackets": [
                        {
                            "bracket": 1,
                            "initialLeverage": 125,
                            "notionalFloor": 0,
                            "notionalCap": 1000000,
                            "maintMarginRatio": 0.01,
                            "cum": 0.0,
                        },
                    ],
                },
            ]

        async def _fetch(symbol: str | None = None) -> list[dict[str, object]]:
            return _response(symbol or "UNKNOWN")

        mock_exchange.futures_get_leverage_brackets = AsyncMock(side_effect=_fetch)
        calc = LiquidationCalculator(mock_exchange)

        await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(10000),
        )
        await calc.estimate_liquidation_price(
            symbol="ETHUSDT",
            side="LONG",
            entry_price=Decimal(3000),
            leverage=10,
            notional=Decimal(10000),
        )

        assert mock_exchange.futures_get_leverage_brackets.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_leverage(self, mock_exchange) -> None:
        calc = LiquidationCalculator(mock_exchange)

        result = await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            leverage=0,
            notional=Decimal(10000),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_entry_price(self, mock_exchange) -> None:
        calc = LiquidationCalculator(mock_exchange)

        result = await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(0),
            leverage=10,
            notional=Decimal(10000),
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_highest_bracket_when_notional_exceeds_caps(
        self, mock_exchange
    ) -> None:
        calc = LiquidationCalculator(mock_exchange)

        liq = await calc.estimate_liquidation_price(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=Decimal(50000),
            leverage=10,
            notional=Decimal(10_000_000),
        )

        # Falls back to the highest bracket: mmr 0.01, cum 1300
        # WB=1_000_000, q=200, cum=1300: (1_000_000 + 1300 - 10_000_000) / (200 * -0.99)
        assert liq == pytest.approx(Decimal("45447.9797979798"), abs=Decimal("1e-6"))
