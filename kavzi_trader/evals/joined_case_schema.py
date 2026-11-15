from pydantic import BaseModel, ConfigDict

from kavzi_trader.evals.case_result_schema import CaseResultSchema
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema

NO_TRADE = "NO_TRADE"
TRADE_SIDES = ("LONG", "SHORT")


class JoinedCaseSchema(BaseModel):
    """A run result next to the dataset case it answered."""

    result: CaseResultSchema
    case: EvalCaseSchema

    model_config = ConfigDict(frozen=True)

    @property
    def trader_side(self) -> str | None:
        """LONG or SHORT only for a valid Trader trade with full geometry."""
        if self.result.stopped_at != "trader":
            return None
        return self._valid_trade_side()

    @property
    def forced_trader_side(self) -> str | None:
        """Like trader_side, for a Trader that ran only because it was forced."""
        return self._valid_trade_side() if self.result.trader_forced else None

    def _valid_trade_side(self) -> str | None:
        trader = self.result.trader
        if trader is None:
            return None
        has_geometry = None not in (trader.entry, trader.stop_loss, trader.take_profit)
        if trader.stop_reason == "ok" and trader.action in TRADE_SIDES and has_geometry:
            return trader.action
        return None

    @property
    def final_action(self) -> str:
        return self.trader_side or NO_TRADE

    @property
    def live_action(self) -> str:
        """The action the live Scout would have allowed; bypassed SKIPs are NO_TRADE."""
        return NO_TRADE if self.result.scout_bypassed else self.final_action
