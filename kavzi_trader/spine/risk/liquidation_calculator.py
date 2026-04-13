import asyncio
import logging
from decimal import Decimal
from typing import Literal, cast

from kavzi_trader.api.binance.client import BinanceClient
from kavzi_trader.api.binance.schemas.data_dicts import (
    LeverageBracketDict,
    LeverageBracketEntryDict,
)

logger = logging.getLogger(__name__)


class LiquidationCalculator:
    """Estimates Binance USD-M futures liquidation prices using tier MMR.

    Wraps `/fapi/v1/leverageBracket` to look up the maintenance margin ratio
    (MMR) for the notional tier covering the position, then applies the
    isolated-margin approximation documented by Binance:
    https://www.binance.com/en/support/faq/how-to-calculate-liquidation-price-of-usd%E2%93%A2-m-futures-contracts-b3c689c1f50a44cabb3a84e663b81d93

    - LONG:  liq = entry * (1 - 1/leverage + MMR)
    - SHORT: liq = entry * (1 + 1/leverage - MMR)

    Bracket data is cached per-symbol; the first lookup hits the network and
    subsequent calls are served locally.
    """

    def __init__(self, exchange: BinanceClient) -> None:
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

        mmr = self._select_mmr(brackets, notional)
        if mmr is None:
            logger.warning(
                "No bracket matched notional=%s for %s; cannot estimate liq",
                notional,
                symbol,
            )
            return None

        inv_leverage = Decimal(1) / Decimal(leverage)
        if side == "LONG":
            liq_price = entry_price * (Decimal(1) - inv_leverage + mmr)
        else:
            liq_price = entry_price * (Decimal(1) + inv_leverage - mmr)

        logger.debug(
            "Liquidation estimate %s side=%s entry=%s leverage=%s MMR=%s liq=%s",
            symbol,
            side,
            entry_price,
            leverage,
            mmr,
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
        raw: list[dict[str, object]] | list[LeverageBracketDict],
        symbol: str,
    ) -> list[LeverageBracketEntryDict] | None:
        if not raw:
            logger.warning("Empty leverage bracket response for %s", symbol)
            return None
        entry = cast("LeverageBracketDict", raw[0])
        brackets = entry.get("brackets")
        if not brackets:
            logger.warning("No brackets in leverage response for %s", symbol)
            return None
        return list(brackets)

    def _select_mmr(
        self,
        brackets: list[LeverageBracketEntryDict],
        notional: Decimal,
    ) -> Decimal | None:
        # Brackets are ordered ascending by notional; pick the first whose
        # cap covers the position. Fall back to the highest bracket if the
        # notional exceeds every cap (should be very rare).
        for bracket in brackets:
            notional_floor = Decimal(str(bracket["notionalFloor"]))
            notional_cap = Decimal(str(bracket["notionalCap"]))
            if notional_floor <= notional <= notional_cap:
                return Decimal(str(bracket["maintMarginRatio"]))
        last = brackets[-1]
        logger.warning(
            "Notional %s above all bracket caps; using highest tier MMR %s",
            notional,
            last["maintMarginRatio"],
        )
        return Decimal(str(last["maintMarginRatio"]))
