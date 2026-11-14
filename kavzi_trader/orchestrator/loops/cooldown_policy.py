import logging

from kavzi_trader.brain.agent.router import PipelineResult
from kavzi_trader.brain.confluence_gates_schema import ConfluenceGatesSchema
from kavzi_trader.brain.confluence_thresholds import (
    CONFLUENCE_REJECT_MAX,
)
from kavzi_trader.domain.analyst_decision import AnalystDecisionSchema
from kavzi_trader.orchestrator.loops.reasoning_config import (
    ReasoningLoopConfigSchema,
)
from kavzi_trader.orchestrator.loops.symbol_state import SymbolStateTracker

logger = logging.getLogger(__name__)

_DIRECTIONS = ("LONG", "SHORT")


class CooldownPolicy:
    """Decides when a symbol or direction sits out reasoning cycles.

    Covers per-direction cooldowns, SKIP suspension, repeated geometry
    rejects and repeated Trader WAITs, all stored in a SymbolStateTracker.
    """

    def __init__(
        self,
        state: SymbolStateTracker,
        config: ReasoningLoopConfigSchema,
        analyst_cooldown_cycles: int,
        max_rejection_multiplier: int,
    ) -> None:
        self._state = state
        self._config = config
        self._analyst_cooldown_cycles = analyst_cooldown_cycles
        self._max_rejection_multiplier = max_rejection_multiplier

    @property
    def max_rejection_multiplier(self) -> int:
        return self._max_rejection_multiplier

    def tick(self, symbol: str) -> bool:
        """Decrement direction cooldowns. Return True if ALL directions are blocked."""
        long_cd = self._state.cooldown(symbol, "LONG")
        short_cd = self._state.cooldown(symbol, "SHORT")

        if long_cd > 0:
            self._state.decrement_cooldown(symbol, "LONG")
        if short_cd > 0:
            self._state.decrement_cooldown(symbol, "SHORT")

        # Only skip when both directions are on cooldown
        return long_cd > 0 and short_cd > 0

    def is_suspended(self, symbol: str) -> bool:
        """Check if a symbol is dynamically suspended due to consecutive SKIPs."""
        skip_interval = self._state.skip_eval_interval(symbol)
        if skip_interval <= 0:
            return False
        skip_count = self._state.consecutive_skips(symbol)
        if skip_count % skip_interval != 0:
            self._state.bump_skip(symbol)
            return True
        return False

    def track_skip_suspension(self, symbol: str, verdict: str) -> None:
        """Update dynamic suspension state based on scout verdict."""
        if verdict != "SKIP":
            self._state.clear_skip_suspension(symbol)
            return
        count = self._state.bump_skip(symbol)
        if count < self._config.skip_suspension_threshold:
            return
        # Falling back to 1 makes the first suspension double to 2.
        current_interval = self._state.skip_eval_interval(symbol) or 1
        new_interval = min(
            max(current_interval * 2, 2),
            self._config.max_skip_eval_interval,
        )
        self._state.set_skip_eval_interval(symbol, new_interval)
        logger.info(
            "Symbol %s suspended: %d consecutive SKIPs, eval every %d cycles",
            symbol,
            count,
            new_interval,
            extra={"symbol": symbol},
        )

    def apply_analyst_cooldown(
        self,
        symbol: str,
        analyst: AnalystDecisionSchema,
        gates: ConfluenceGatesSchema,
    ) -> None:
        """Apply a hysteresis-banded cooldown based on the Analyst verdict.

        ``gates`` are the signal-scaled thresholds from the Analyst stage; the
        reject and low bands shift down with them when signals are missing.

        Score <= 3 and invalid escalates per direction; borderline or
        high-confluence-but-invalid gets one light cooldown; a valid setup at
        the regime entry gate clears rejection counts.
        """
        score = analyst.confluence_score
        setup_valid = analyst.setup_valid
        direction = analyst.direction
        cooldown_dirs = list(_DIRECTIONS) if direction == "NEUTRAL" else [direction]

        regime_gate = gates.regime_gate
        if not setup_valid and score <= gates.adjusted(CONFLUENCE_REJECT_MAX):
            for d in cooldown_dirs:
                count = self._state.bump_rejection(symbol, d)
                base_cooldown = self.compute_rejection_cooldown(score, gates)
                multiplier = min(count, self._max_rejection_multiplier)
                self._state.set_cooldown(symbol, d, base_cooldown * multiplier)
                logger.debug(
                    "Consecutive rejection %d for %s %s: cooldown=%d (base=%d x %d)",
                    count,
                    symbol,
                    d,
                    base_cooldown * multiplier,
                    base_cooldown,
                    multiplier,
                )
            return

        if not setup_valid or score < regime_gate:
            borderline_cycles = self._config.borderline_cooldown_cycles
            for d in cooldown_dirs:
                existing = self._state.cooldown(symbol, d)
                self._state.set_cooldown(symbol, d, max(existing, borderline_cycles))
            logger.debug(
                "Borderline analyst %s direction=%s score=%d setup_valid=%s"
                " gate=%d → cooldown=%d (no escalation)",
                symbol,
                direction,
                score,
                setup_valid,
                regime_gate,
                borderline_cycles,
            )
            return

        for d in cooldown_dirs:
            self._state.clear_rejections(symbol, d)

    def compute_rejection_cooldown(
        self, confluence_score: int, gates: ConfluenceGatesSchema
    ) -> int:
        """Scale rejection cooldown within the aggressive band (score <= 3)."""
        low_band = gates.adjusted(self._config.cooldown_low_confluence_threshold)
        multiplier = 3 if confluence_score <= low_band else 2
        cooldown = self._analyst_cooldown_cycles * multiplier
        logger.debug(
            "Rejection cooldown: confluence=%d multiplier=%d cooldown=%d cycles",
            confluence_score,
            multiplier,
            cooldown,
        )
        return cooldown

    def track_geometry_rejects(self, symbol: str, result: PipelineResult) -> None:
        """Cool the symbol down once the Trader's SL/TP keeps failing R:R checks.

        Repeated geometry rejects mean the setup isn't tradeable right now, so
        further LLM calls would only burn budget on the same outcome.
        """
        if result.trader_stop_reason == "geometry_reject":
            count = self._state.bump_geometry_reject(symbol)
            cfg = self._config
            if count >= cfg.geometry_reject_cooldown_threshold:
                for d in _DIRECTIONS:
                    self._state.set_cooldown(
                        symbol, d, cfg.geometry_reject_cooldown_cycles
                    )
                self._state.clear_geometry_rejects(symbol)
                logger.info(
                    "Geometry reject cooldown for %s: %d consecutive rejects"
                    " → both directions suppressed for %d cycles",
                    symbol,
                    count,
                    cfg.geometry_reject_cooldown_cycles,
                    extra={"symbol": symbol},
                )
        elif result.trader_stop_reason in {"ok", "dedup_hit"}:
            self._state.clear_geometry_rejects(symbol)

    def track_consecutive_waits(self, symbol: str, result: PipelineResult) -> None:
        """Apply escalating cooldown after repeated Trader WAITs."""
        if result.trader is None or result.trader.action != "WAIT":
            return
        direction = (
            result.analyst.direction if result.analyst is not None else "NEUTRAL"
        )
        wait_dirs = list(_DIRECTIONS) if direction == "NEUTRAL" else [direction]
        wait_threshold = self._config.wait_cooldown_threshold
        for d in wait_dirs:
            count = self._state.bump_wait(symbol, d)
            if count >= wait_threshold:
                excess = count - wait_threshold + 1
                cooldown = min(
                    self._config.wait_cooldown_base_cycles * excess,
                    self._config.wait_max_cooldown_cycles,
                )
                self._state.set_cooldown(symbol, d, cooldown)
                logger.info(
                    "Consecutive WAIT %d for %s %s: cooldown=%d cycles",
                    count,
                    symbol,
                    d,
                    cooldown,
                )

    def start_post_trade_cooldown(self, symbol: str) -> None:
        """Cool both directions after an enqueue and reset WAIT/geometry counters."""
        post_trade_cooldown = self._analyst_cooldown_cycles * 3
        for d in _DIRECTIONS:
            self._state.set_cooldown(symbol, d, post_trade_cooldown)
            self._state.clear_waits(symbol, d)
        self._state.clear_geometry_rejects(symbol)
