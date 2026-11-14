import asyncio
import logging
from decimal import Decimal
from typing import Literal

from kavzi_trader.api.binance.schemas.data_dicts import (
    LeverageBracketDict,
    LeverageBracketEntryDict,
)
from kavzi_trader.api.exchange_client import ExchangeClient

logger = logging.getLogger(__name__)


class LiquidationCalculator:
    """Estimates Binance USD-M one-way isolated liquidation prices.

    Uses the official formula with the per-bracket maintenance amount (cum):
    https://www.binance.com/en/support/faq/how-to-calculate-liquidation-price-of-usd%E2%93%A2-m-futures-contracts-b3c689c1f50a44cabb3a84e663b81d93

        liq = (WB + cum - side * qty * entry) / (qty * (MMR - side))

    side is +1 for LONG, -1 for SHORT. For an isolated position WB is the
    initial margin (notional / leverage); fees are ignored. Brackets come
    from `/fapi/v1/leverageBracket` and are cached per symbol.
    """

    def __init__(self, exchange: ExchangeClient) -> None:
        self._exchange = exchange
        self._bracket_cache: dict[str, list[LeverageBracketEntryDict]] = {}
        self._lock = asyncio.Lock()

    async def estimate_liquidation_price(
        self,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        entry_price: Decimal,
        leverage: int,
        notional: Decimal,
    ) -> Decimal | None:
        if leverage <= 0:
            logger.warning(
                "Invalid leverage %s for %s; cannot estimate liquidation",
                leverage,
                symbol,
            )
            return None
        if entry_price <= 0 or notional <= 0:
            logger.warning(
                "Invalid entry_price=%s or notional=%s for %s",
                entry_price,
                notional,
                symbol,
            )
            return None

        brackets = await self._get_brackets(symbol)
        if brackets is None:
            return None

        bracket = self._select_bracket(brackets, notional)
        mmr = Decimal(str(bracket["maintMarginRatio"]))
        cum = Decimal(str(bracket["cum"]))

        side_sign = Decimal(1) if side == "LONG" else Decimal(-1)
        quantity = notional / entry_price
        wallet_balance = notional / Decimal(leverage)
        liq_price = (wallet_balance + cum - side_sign * quantity * entry_price) / (
            quantity * (mmr - side_sign)
        )

        logger.debug(
            "Liquidation estimate %s side=%s entry=%s leverage=%s MMR=%s cum=%s liq=%s",
            symbol,
            side,
            entry_price,
            leverage,
            mmr,
            cum,
            liq_price,
        )
        return liq_price

    async def _get_brackets(
        self,
        symbol: str,
    ) -> list[LeverageBracketEntryDict] | None:
        cached = self._bracket_cache.get(symbol)
        if cached is not None:
            return cached

        async with self._lock:
            cached = self._bracket_cache.get(symbol)
            if cached is not None:
                return cached
            try:
                raw = await self._exchange.futures_get_leverage_brackets(symbol=symbol)
            except Exception:
                logger.exception(
                    "Failed to fetch leverage brackets for %s",
                    symbol,
                )
                return None

            brackets = self._extract_brackets(raw, symbol)
            if brackets is None:
                return None

            self._bracket_cache[symbol] = brackets
            logger.debug(
                "Cached %d leverage brackets for %s",
                len(brackets),
                symbol,
            )
            return brackets

    def _extract_brackets(
        self,
        raw: list[LeverageBracketDict],
        symbol: str,
    ) -> list[LeverageBracketEntryDict] | None:
        if not raw:
            logger.warning("Empty leverage bracket response for %s", symbol)
            return None
        brackets = raw[0].get("brackets")
        if not brackets:
            logger.warning("No brackets in leverage response for %s", symbol)
            return None
        return list(brackets)

    def _select_bracket(
        self,
        brackets: list[LeverageBracketEntryDict],
        notional: Decimal,
    ) -> LeverageBracketEntryDict:
        # Brackets are ordered ascending by notional; pick the first whose
        # cap covers the position. Fall back to the highest bracket if the
        # notional exceeds every cap (should be very rare).
        for bracket in brackets:
            notional_floor = Decimal(str(bracket["notionalFloor"]))
            notional_cap = Decimal(str(bracket["notionalCap"]))
            if notional_floor <= notional <= notional_cap:
                return bracket
        last = brackets[-1]
        logger.warning(
            "Notional %s above all bracket caps; using highest tier MMR %s",
            notional,
            last["maintMarginRatio"],
        )
        return last
