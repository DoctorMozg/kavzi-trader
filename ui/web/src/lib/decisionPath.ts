import { bufferVerdict, sizeIfLong } from "@/lib/explain";
import { fmtDuration, fmtPlainPct, fmtPrice } from "@/lib/format";
import type { Decision, OpenPosition, Trade, TrendState, TrendSymbol } from "@/lib/protocol";
import { exitName, fmtUtcHour, spikeRatio } from "@/lib/trend";

export interface PathStep {
  key: "direction" | "size" | "target" | "held" | "halving" | "order" | "stop";
  // How this step combines with the one above it.
  via: string | null;
  label: string;
  value: string;
  text: string;
}

export interface DecisionPath {
  steps: PathStep[];
  next: string;
}

export interface PathInput {
  state: TrendState;
  symbol: TrendSymbol;
  price: number;
  position: OpenPosition | null;
  decisions: Decision[];
  trades: Trade[];
  nowMs: number;
}

const pct = (weight: number): string => fmtPlainPct(weight * 100);

function signedPct(from: number, to: number): string {
  const move = (to / from - 1) * 100;
  return `${move >= 0 ? "+" : ""}${move.toFixed(1)}%`;
}

function lastOrder(input: PathInput): { value: string; ts: number } | null {
  const name = input.symbol.symbol;
  const skip = input.decisions.findLast((d) => d.symbol === name && d.stage === "execution");
  const trade = input.trades.findLast((t) => t.symbol === name);
  const ago = (ts: number): string => `${fmtDuration(input.nowMs - ts)} ago`;
  const fromSkip = skip && { value: `not traded ${ago(skip.ts_ms)}`, ts: skip.ts_ms };
  const fromTrade = trade && { value: `${trade.side} ${trade.status.toLowerCase()} ${ago(trade.ts_ms)}`, ts: trade.ts_ms };
  if (fromSkip && fromTrade) return fromSkip.ts > fromTrade.ts ? fromSkip : fromTrade;
  return fromSkip ?? fromTrade ?? null;
}

function halvingStep(state: TrendState, symbol: TrendSymbol): PathStep | null {
  const rule = state.vol_spike;
  if (rule === null) return null;
  const days = Math.round(rule.history_hours / 24);
  const p = `p${Math.round(rule.quantile * 100)}`;
  const halving = symbol.halving;
  const ratio = spikeRatio(symbol.spike);
  const base = { key: "halving", via: "↓ hourly vol check", label: "Spike halving" } as const;
  if (halving !== null) {
    return {
      ...base,
      value: `halved → ${pct(halving.target_weight)}`,
      text: `The ${fmtUtcHour(halving.hour_ms)} hour's 1-minute variance was ${(halving.rv / halving.threshold).toFixed(1)}× the ${p} of the previous ${days} days, so ${pct(1 - rule.scale)} of the position was sold. The next daily rebalance restores the rule's weight.`,
    };
  }
  if (symbol.held_weight === 0) {
    return { ...base, value: "off", text: "Checked every hour only while the coin is held." };
  }
  return {
    ...base,
    value: ratio === null ? (symbol.spike === null ? "pending" : "warming up") : `${ratio.toFixed(2)}× threshold`,
    text: `Every hour, the last hour's 1-minute variance is compared with the ${p} of the previous ${days} days of hours. Above 1×, ${pct(1 - rule.scale)} of the position is sold until the next daily rebalance.`,
  };
}

export function buildDecisionPath(input: PathInput): DecisionPath {
  const { state, symbol, price, position } = input;
  const isLong = symbol.signal > 0;
  const n = state.lookback;
  const size = sizeIfLong(state, symbol);
  const order = lastOrder(input);
  const steps = [
    {
      key: "direction",
      via: null,
      label: "Direction",
      value: isLong ? "LONG · 1" : "FLAT · 0",
      text: isLong
        ? `A daily close broke above the ${n}-day high and none has closed below the ${exitName(state)} (${fmtPrice(symbol.exit_level)}) since.`
        : `No daily close above the ${n}-day high (${fmtPrice(symbol.entry_level)}) since the last close below the ${exitName(state)}. Long/flat rule: it never goes SHORT.`,
    },
    {
      key: "size",
      via: "×",
      label: "Size if long",
      value: size === null ? "-" : pct(size),
      text:
        symbol.annual_vol === null || size === null
          ? `Needs ${state.vol_window} daily returns before it can size.`
          : `min(${pct(state.annual_vol_target)} target ÷ ${pct(symbol.annual_vol)} vol, ${state.max_leverage}× cap) ÷ ${state.symbols.length} symbols. Calmer coins get more weight, so each adds similar risk.`,
    },
    {
      key: "target",
      via: "=",
      label: "Target",
      value: pct(symbol.target_weight),
      text: "Share of equity the rule wants in this coin today.",
    },
    {
      key: "held",
      via: `↓ ${pct(state.buffer_band)} turnover buffer`,
      label: "Held",
      value: pct(symbol.held_weight),
      text: bufferVerdict(symbol.target_weight, symbol.held_weight, state.buffer_band).text,
    },
    halvingStep(state, symbol),
    {
      key: "order",
      via: "↓ executor",
      label: "Order",
      value: order?.value ?? "none",
      text: "Converts held weight to a quantity at the live price; skips changes under the minimum notional and rejects ones that fail risk checks.",
    },
    {
      key: "stop",
      via: "↓ while held",
      label: "Disaster stop",
      value: position ? fmtPrice(Number(position.stop_loss)) : "off",
      text: position
        ? `Resting stop ${pct(state.disaster_stop_pct)} below the fill; fires only on a crash between daily closes.`
        : `Arms ${pct(state.disaster_stop_pct)} below the fill when a position opens.`,
    },
  ].filter((step): step is PathStep => step !== null);
  const next = isLong
    ? `Exit only if a 00:00 UTC close lands below ${fmtPrice(symbol.exit_level)} (${signedPct(price, symbol.exit_level)} from ${fmtPrice(price)}). That takes it FLAT, never SHORT.`
    : `Enter only if a 00:00 UTC close lands above ${fmtPrice(symbol.entry_level)} (${signedPct(price, symbol.entry_level)} from ${fmtPrice(price)}). That buys ${size === null ? "a vol-sized position" : pct(size)} of equity. Falling further changes nothing: there are no shorts.`;
  return { steps, next };
}
