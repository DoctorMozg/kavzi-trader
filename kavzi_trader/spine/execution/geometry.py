import logging
from decimal import Decimal

from kavzi_trader.brain.schemas.analyst import KeyLevelSchema
from kavzi_trader.commons.trading_constants import MAX_TP_ATR, SL_LEVEL_BUFFER_ATR
from kavzi_trader.spine.execution.geometry_schemas import (
    GeometryInputsSchema,
    GeometryRejectionCode,
    GeometryRejectionSchema,
    GeometryViabilitySchema,
    TradeDirection,
    TradeGeometrySchema,
    TradeStructureSchema,
)
from kavzi_trader.spine.risk.config import RiskConfigSchema

logger = logging.getLogger(__name__)

_HUNDRED = Decimal(100)


def _profit_side_desc(direction: TradeDirection) -> str:
    """Human-readable level a LONG/SHORT anchors against, for reject messages."""
    return "SUPPORT below" if direction == "LONG" else "RESISTANCE above"


class _ResolvedStop:
    """Internal carrier for a resolved stop distance and its adjustments."""

    __slots__ = ("adjustments", "distance")

    def __init__(self, distance: Decimal, adjustments: list[str]) -> None:
        self.distance = distance
        self.adjustments = adjustments


class TradeGeometryCalculator:
    """
    Deterministic trade-geometry engine.

    Turns the Trader agent's structural choices (stop anchor, target style,
    entry tactic) into exact entry / stop-loss / take-profit prices that are
    guaranteed to satisfy the configured minimum risk:reward ratio, or
    returns a typed rejection explaining why no legal geometry exists.

    Also provides ``estimate`` — a cheap viability check used before the
    expensive Trader LLM call: "could any legal structure reach min R:R
    here?" using the tightest legal stop and the best available target.
    """

    def __init__(self, risk_config: RiskConfigSchema) -> None:
        self._config = risk_config

    def compute(
        self,
        structure: TradeStructureSchema,
        inputs: GeometryInputsSchema,
    ) -> TradeGeometrySchema | GeometryRejectionSchema:
        """Derive concrete prices for ``structure``, or reject with a reason."""
        atr = inputs.atr_14
        if atr is None or atr <= 0:
            return self._reject(
                inputs, "NO_ATR", "ATR unavailable; cannot derive stop distance."
            )

        entry = self._resolve_entry(structure, inputs)
        if isinstance(entry, GeometryRejectionSchema):
            return entry

        stop = self._resolve_stop_distance(structure, inputs, entry, atr)
        if isinstance(stop, GeometryRejectionSchema):
            return stop

        liq_reject = self._check_liquidation_budget(inputs, entry, stop.distance)
        if liq_reject is not None:
            return liq_reject

        target = self._resolve_target_distance(
            structure, inputs, entry, atr, stop.distance, stop.adjustments
        )
        if isinstance(target, GeometryRejectionSchema):
            return target

        return self._assemble(structure, inputs, entry, stop, target, atr)

    def _assemble(
        self,
        structure: TradeStructureSchema,
        inputs: GeometryInputsSchema,
        entry: Decimal,
        stop: "_ResolvedStop",
        target: Decimal,
        atr: Decimal,
    ) -> TradeGeometrySchema | GeometryRejectionSchema:
        """Combine resolved entry/stop/target into directional prices."""
        sign = Decimal(1) if structure.direction == "LONG" else Decimal(-1)
        stop_loss = entry - sign * stop.distance
        take_profit = entry + sign * target
        if stop_loss <= 0 or take_profit <= 0:
            return self._reject(
                inputs,
                "TP_UNREACHABLE",
                "Derived prices are non-positive; structure unusable.",
            )

        geometry = TradeGeometrySchema(
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            rr_ratio=target / stop.distance,
            sl_atr_multiple=stop.distance / atr,
            adjustments=stop.adjustments,
        )
        logger.debug(
            "Geometry computed for %s: dir=%s entry=%s sl=%s tp=%s rr=%s adj=%s",
            inputs.symbol,
            structure.direction,
            geometry.entry,
            geometry.stop_loss,
            geometry.take_profit,
            geometry.rr_ratio,
            geometry.adjustments,
        )
        return geometry

    def estimate(
        self,
        direction: TradeDirection,
        inputs: GeometryInputsSchema,
    ) -> GeometryViabilitySchema:
        """
        Check whether any legal geometry can reach min R:R for ``direction``.

        Uses the tightest legal stop distance against the best available
        target (deepest ATR projection or the furthest profit-side key
        level), so a "not viable" verdict means even the most favourable
        structural choice cannot work — safe to skip the Trader LLM call.
        """
        atr = inputs.atr_14
        if atr is None or atr <= 0:
            return GeometryViabilitySchema(
                viable=False,
                best_rr=None,
                reason="ATR unavailable; cannot estimate geometry.",
            )
        price = inputs.current_price
        min_distance = self._min_stop_distance(price, atr)
        max_distance = self._config.max_sl_atr * atr
        if min_distance > max_distance:
            return GeometryViabilitySchema(
                viable=False,
                best_rr=None,
                reason=(
                    f"Minimum stop distance {min_distance} (percent floor)"
                    f" exceeds max {self._config.max_sl_atr}x ATR — ATR too"
                    f" compressed for a legal stop."
                ),
            )
        liquidation_budget = self._liquidation_budget(price, inputs.leverage)
        if liquidation_budget is not None and min_distance > liquidation_budget:
            return GeometryViabilitySchema(
                viable=False,
                best_rr=None,
                reason=(
                    f"Minimum stop distance {min_distance} exceeds the"
                    f" liquidation buffer budget {liquidation_budget} at"
                    f" {inputs.leverage}x leverage."
                ),
            )

        best_target = MAX_TP_ATR * atr
        furthest_level = self._furthest_profit_level_distance(
            direction, price, inputs.key_levels
        )
        if furthest_level is not None and furthest_level > best_target:
            best_target = furthest_level

        best_rr = best_target / min_distance
        viable = best_rr >= self._config.min_rr_ratio
        return GeometryViabilitySchema(
            viable=viable,
            best_rr=best_rr,
            reason=None
            if viable
            else (
                f"Best achievable R:R {best_rr:.2f} below minimum"
                f" {self._config.min_rr_ratio} (tightest stop {min_distance},"
                f" best target {best_target})."
            ),
        )

    def _resolve_entry(
        self,
        structure: TradeStructureSchema,
        inputs: GeometryInputsSchema,
    ) -> Decimal | GeometryRejectionSchema:
        if structure.entry_tactic == "IMMEDIATE":
            return inputs.current_price

        index = structure.entry_level_index
        if index is None:
            return self._reject(
                inputs,
                "INVALID_STRUCTURE",
                "PULLBACK_TO_LEVEL requires entry_level_index.",
            )
        level = self._level_at(inputs, index)
        if level is None:
            return self._reject(
                inputs,
                "INVALID_STRUCTURE",
                f"entry_level_index {index} out of range"
                f" (have {len(inputs.key_levels)} levels).",
            )
        if structure.direction == "LONG":
            valid = level.level_type == "SUPPORT" and level.price < inputs.current_price
        else:
            valid = (
                level.level_type == "RESISTANCE" and level.price > inputs.current_price
            )
        if not valid:
            return self._reject(
                inputs,
                "INVALID_STRUCTURE",
                f"Pullback entry for {structure.direction} requires a"
                f" {_profit_side_desc(structure.direction)}"
                f" current price; got {level.level_type} at {level.price}.",
            )
        return level.price

    def _resolve_stop_distance(
        self,
        structure: TradeStructureSchema,
        inputs: GeometryInputsSchema,
        entry: Decimal,
        atr: Decimal,
    ) -> _ResolvedStop | GeometryRejectionSchema:
        adjustments: list[str] = []

        if structure.stop_level_index is not None:
            level = self._level_at(inputs, structure.stop_level_index)
            if level is None:
                return self._reject(
                    inputs,
                    "INVALID_STRUCTURE",
                    f"stop_level_index {structure.stop_level_index} out of"
                    f" range (have {len(inputs.key_levels)} levels).",
                )
            if structure.direction == "LONG":
                anchored = level.level_type == "SUPPORT" and level.price < entry
            else:
                anchored = level.level_type == "RESISTANCE" and level.price > entry
            if not anchored:
                return self._reject(
                    inputs,
                    "INVALID_STRUCTURE",
                    f"Stop anchor for {structure.direction} must be a"
                    f" {_profit_side_desc(structure.direction)}"
                    f" entry; got {level.level_type} at {level.price}.",
                )
            buffer = SL_LEVEL_BUFFER_ATR * atr
            distance = abs(entry - level.price) + buffer
        elif structure.stop_atr_multiplier is not None:
            multiplier = structure.stop_atr_multiplier
            if not (self._config.min_sl_atr <= multiplier <= self._config.max_sl_atr):
                return self._reject(
                    inputs,
                    "INVALID_STRUCTURE",
                    f"stop_atr_multiplier {multiplier} outside"
                    f" [{self._config.min_sl_atr}, {self._config.max_sl_atr}].",
                )
            distance = multiplier * atr
        else:
            return self._reject(
                inputs,
                "INVALID_STRUCTURE",
                "Stop anchor missing: provide stop_level_index or stop_atr_multiplier.",
            )

        min_distance = self._min_stop_distance(entry, atr)
        if distance < min_distance:
            adjustments.append(
                f"stop widened from {distance} to minimum {min_distance}"
            )
            distance = min_distance

        max_distance = self._config.max_sl_atr * atr
        if distance > max_distance:
            return self._reject(
                inputs,
                "SL_TOO_WIDE",
                f"Stop distance {distance} exceeds {self._config.max_sl_atr}x"
                f" ATR ({max_distance}); structure unsuitable.",
            )
        return _ResolvedStop(distance=distance, adjustments=adjustments)

    def _check_liquidation_budget(
        self,
        inputs: GeometryInputsSchema,
        entry: Decimal,
        stop_distance: Decimal,
    ) -> GeometryRejectionSchema | None:
        budget = self._liquidation_budget(entry, inputs.leverage)
        if budget is not None and stop_distance > budget:
            return self._reject(
                inputs,
                "SL_BEYOND_LIQUIDATION",
                f"Stop distance {stop_distance} exceeds the liquidation buffer"
                f" budget {budget} at {inputs.leverage}x leverage.",
            )
        return None

    def _resolve_target_distance(
        self,
        structure: TradeStructureSchema,
        inputs: GeometryInputsSchema,
        entry: Decimal,
        atr: Decimal,
        stop_distance: Decimal,
        adjustments: list[str],
    ) -> Decimal | GeometryRejectionSchema:
        min_rr = self._config.min_rr_ratio
        required = min_rr * stop_distance

        if structure.target_style == "STRUCTURAL":
            structural = self._nearest_qualifying_level_distance(
                structure.direction, entry, inputs.key_levels, required
            )
            if structural is not None:
                return structural
            adjustments.append(
                "no structural level reaches min R:R; extended to ATR target"
            )
        else:
            atr_multiple = (
                Decimal(2) if structure.target_style == "ATR_2X" else (Decimal(3))
            )
            candidate = atr_multiple * atr
            if candidate >= required:
                return candidate
            adjustments.append(
                f"{structure.target_style} target extended to meet min R:R"
            )

        if required <= MAX_TP_ATR * atr:
            return required
        return self._reject(
            inputs,
            "TP_UNREACHABLE",
            f"Meeting min R:R {min_rr} needs a target {required} away, beyond"
            f" the realistic {MAX_TP_ATR}x ATR ceiling ({MAX_TP_ATR * atr})."
            f" Stop is too wide for a viable trade.",
        )

    def _min_stop_distance(self, reference_price: Decimal, atr: Decimal) -> Decimal:
        atr_floor = self._config.min_sl_atr * atr
        percent_floor = self._config.min_sl_percent / _HUNDRED * reference_price
        return max(atr_floor, percent_floor)

    def _liquidation_budget(self, entry: Decimal, leverage: int) -> Decimal | None:
        """Max stop distance that keeps the configured buffer to liquidation.

        Uses the conservative no-MMR approximation (liquidation at
        entry/leverage); the risk validator downstream re-checks against
        real Binance maintenance-margin brackets.
        """
        if leverage <= 1:
            return None
        liquidation_distance = entry / Decimal(leverage)
        return liquidation_distance * (1 - self._config.liquidation_sl_buffer_ratio)

    @staticmethod
    def _level_at(inputs: GeometryInputsSchema, index: int) -> KeyLevelSchema | None:
        if 0 <= index < len(inputs.key_levels):
            return inputs.key_levels[index]
        return None

    @staticmethod
    def _nearest_qualifying_level_distance(
        direction: TradeDirection,
        entry: Decimal,
        key_levels: list[KeyLevelSchema],
        required_distance: Decimal,
    ) -> Decimal | None:
        """Nearest profit-side level at least ``required_distance`` away.

        Nearest-first keeps hit probability as high as possible while still
        clearing the min R:R bar.
        """
        if direction == "LONG":
            distances = [
                lv.price - entry
                for lv in key_levels
                if lv.level_type == "RESISTANCE" and lv.price > entry
            ]
        else:
            distances = [
                entry - lv.price
                for lv in key_levels
                if lv.level_type == "SUPPORT" and lv.price < entry
            ]
        qualifying = [d for d in distances if d >= required_distance]
        return min(qualifying) if qualifying else None

    @staticmethod
    def _furthest_profit_level_distance(
        direction: TradeDirection,
        price: Decimal,
        key_levels: list[KeyLevelSchema],
    ) -> Decimal | None:
        if direction == "LONG":
            distances = [
                lv.price - price
                for lv in key_levels
                if lv.level_type == "RESISTANCE" and lv.price > price
            ]
        else:
            distances = [
                price - lv.price
                for lv in key_levels
                if lv.level_type == "SUPPORT" and lv.price < price
            ]
        return max(distances) if distances else None

    @staticmethod
    def _reject(
        inputs: GeometryInputsSchema,
        code: GeometryRejectionCode,
        detail: str,
    ) -> GeometryRejectionSchema:
        rejection = GeometryRejectionSchema(code=code, detail=detail)
        logger.info(
            "Geometry rejected for %s: %s — %s",
            inputs.symbol,
            rejection.code,
            rejection.detail,
            extra={"symbol": inputs.symbol, "geometry_rejection": rejection.code},
        )
        return rejection
