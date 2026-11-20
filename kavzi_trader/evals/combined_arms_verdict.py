from kavzi_trader.evals.combined_arms_result_schema import CombinedArmsResultSchema

# Half of mid-exit's separate Sharpe gain on the trading 8 (0.640 to 0.905).
MIN_MID_GAIN = 0.13
# Same bar the halving rule was adopted under (2026_11_19_crash_replay.md).
MAX_HALVING_COST = 0.05
# Sharpe the 2026-11-19 reports gave, on the same data, for the reproduction check.
REPRODUCED = {"base": 0.640, "mid": 0.905, "halving": 0.624}
REPRODUCTION_TOLERANCE = 0.002


class CombinedArmsVerdict:
    """Maps the combined-arms scores to the preregistered keep/drop decisions."""

    def reproduction_errors(self, result: CombinedArmsResultSchema) -> list[str]:
        scored = {
            "base": result.base,
            "mid": result.mid,
            "halving": result.halving,
        }
        errors = []
        for arm, expected in REPRODUCED.items():
            sharpe = scored[arm].net.sharpe
            if sharpe is None or abs(sharpe - expected) > REPRODUCTION_TOLERANCE:
                errors.append(
                    f"{arm}: Sharpe {sharpe}, 2026-11-19 reports gave {expected}"
                )
        return errors

    def keep_mid(self, result: CombinedArmsResultSchema) -> bool:
        return result.mid_gain_with_halving.difference >= MIN_MID_GAIN

    def keep_halving(self, result: CombinedArmsResultSchema) -> bool:
        return -result.halving_change_under_mid.difference <= MAX_HALVING_COST

    def paper_rule(self, result: CombinedArmsResultSchema) -> str:
        mid, halving = self.keep_mid(result), self.keep_halving(result)
        if mid and halving:
            return "mid exit + vol-spike halving (unchanged)"
        if mid:
            return "mid exit only: switch vol_spike off"
        if halving:
            return "low exit + vol-spike halving: switch exit_rule to low"
        return "low exit, no halving: switch exit_rule to low and vol_spike off"
