import { fmtPlainPct, fmtPrice } from "@/lib/format";
import type { TrendState, TrendSymbol } from "@/lib/protocol";

export interface ExplainStep {
  label: string;
  text: string;
}

export interface BufferVerdict {
  trades: boolean;
  text: string;
}

const pct = (weight: number): string => fmtPlainPct(weight * 100);

// Mirrors TurnoverBuffer._trade_mask: flatten, sign flip, or drift past the band.
export function bufferVerdict(target: number, held: number, band: number): BufferVerdict {
  if (target === 0 && held === 0) return { trades: false, text: "Nothing held and nothing targeted, so no trade." };
  if (target === 0) return { trades: true, text: `Target is 0 while holding ${pct(held)}, so the position closes.` };
  if (Math.sign(target) !== Math.sign(held)) {
    return { trades: true, text: `Target ${pct(target)} from flat is a new entry, so it trades.` };
  }
  const limit = band * Math.abs(held);
  if (Math.abs(target - held) > limit) {
    return {
      trades: true,
      text: `Target ${pct(target)} differs from held ${pct(held)} by more than ${pct(limit)} (${pct(band)} of held), so it resizes.`,
    };
  }
  return {
    trades: false,
    text: `Target ${pct(target)} is within ${pct(limit)} (${pct(band)} of held ${pct(held)}), so it keeps the position to save fees.`,
  };
}

export function sizeIfLong(state: TrendState, symbol: TrendSymbol): number | null {
  if (symbol.annual_vol === null || symbol.annual_vol === 0) return null;
  const scale = Math.min(state.annual_vol_target / symbol.annual_vol, state.max_leverage);
  return scale / state.symbols.length;
}

export function trendSteps(state: TrendState, symbol: TrendSymbol, price: number): ExplainStep[] {
  const isLong = symbol.signal > 0;
  const n = state.lookback;
  const steps: ExplainStep[] = [
    {
      label: "Signal",
      text: isLong
        ? `Long since a daily close broke above the prior ${n}-day high, with no close below the ${n}-day low since.`
        : `Flat: no daily close above the prior ${n}-day high since the last close below the ${n}-day low.`,
    },
  ];
  const weight = sizeIfLong(state, symbol);
  if (symbol.annual_vol === null || weight === null) {
    steps.push({ label: "Size", text: `Volatility is still warming up (${state.vol_window} days needed), so size is 0.` });
  } else {
    steps.push({
      label: "Volatility",
      text: `${state.vol_window}-day realised vol is ${pct(symbol.annual_vol)} a year (daily log-return std × √365).`,
    });
    steps.push({
      label: "Size if long",
      text:
        `min(${pct(state.annual_vol_target)} target ÷ ${pct(symbol.annual_vol)} vol, ${state.max_leverage}× cap) ` +
        `÷ ${state.symbols.length} symbols = ${pct(weight)} of equity.`,
    });
  }
  steps.push({ label: "Target", text: `Signal ${symbol.signal} × size = ${pct(symbol.target_weight)} of equity.` });
  steps.push({
    label: "Buffer",
    text: bufferVerdict(symbol.target_weight, symbol.held_weight, state.buffer_band).text,
  });
  if (isLong) {
    steps.push({
      label: "Disaster stop",
      text: `A resting stop ${pct(state.disaster_stop_pct)} below the fill price guards against a crash between daily closes.`,
    });
  }
  const level = isLong ? symbol.exit_level : symbol.entry_level;
  const move = (level / price - 1) * 100;
  steps.push({
    label: "Next flip",
    text:
      `A daily close ${isLong ? "below" : "above"} ${fmtPrice(level)} (${move >= 0 ? "+" : ""}${move.toFixed(1)}% from ${fmtPrice(price)}) ` +
      `turns it ${isLong ? "FLAT" : "LONG"}. Only the 00:00 UTC close counts; intraday moves past the level do not.`,
  });
  return steps;
}
