import type { ClosedPosition, OpenPosition, Trade, TrendState, TrendSymbol, VolSpikeReading } from "@/lib/protocol";

export const DAY_MS = 86_400_000;

export const dayStartMs = (ms: number): number => Math.floor(ms / DAY_MS) * DAY_MS;

// 0 at the exit level, 1 at the entry level, clamped to the channel.
export function channelPosition(price: number, low: number, high: number): number {
  if (high <= low) return 0.5;
  return Math.min(1, Math.max(0, (price - low) / (high - low)));
}

// What a close must fall below to go FLAT, in words.
export function exitName(state: Pick<TrendState, "exit_rule" | "lookback">): string {
  return state.exit_rule === "mid" ? `${state.lookback}-day midpoint` : `${state.lookback}-day low`;
}

export function exitRuleText(state: Pick<TrendState, "exit_rule" | "lookback">): string {
  const n = state.lookback;
  return state.exit_rule === "mid"
    ? `Midpoint of the previous ${n} daily closes' high and low. A close below it turns the symbol FLAT (mid-channel exit, adopted 2026-11-20).`
    : `Lowest of the last ${n} daily closes. A close below it turns the symbol FLAT.`;
}

// The last closed hour's variance as a multiple of its spike threshold.
export function spikeRatio(reading: VolSpikeReading | null): number | null {
  if (reading === null || reading.threshold === null || reading.threshold <= 0) return null;
  return reading.rv / reading.threshold;
}

export const fmtUtcHour = (ms: number): string => `${String(new Date(ms).getUTCHours()).padStart(2, "0")}:00 UTC`;

export interface FlipDistance {
  target: "entry" | "exit";
  pct: number;
}

// The move a daily close needs, from the current price, to flip the rule's state.
export function flipDistance(symbol: TrendSymbol, price: number): FlipDistance {
  return symbol.signal > 0
    ? { target: "exit", pct: (symbol.exit_level / price - 1) * 100 }
    : { target: "entry", pct: (symbol.entry_level / price - 1) * 100 };
}

export interface TradeMark {
  dayMs: number;
  kind: "entry" | "exit";
  text: string;
}

// Entries come from filled long trades, exits from closed positions, so a
// rebalance close and a disaster stop each mark once.
export function tradeMarks(symbol: string, trades: Trade[], closed: ClosedPosition[]): TradeMark[] {
  const entries: TradeMark[] = trades
    .filter((t) => t.symbol === symbol && t.side === "LONG" && t.status === "FILLED")
    .map((t) => ({ dayMs: dayStartMs(t.ts_ms), kind: "entry", text: "Long" }));
  const exits: TradeMark[] = closed
    .filter((c) => c.symbol === symbol)
    .map((c) => ({ dayMs: dayStartMs(c.ts_ms), kind: "exit", text: c.close_reason }));
  return [...entries, ...exits].sort((a, b) => a.dayMs - b.dayMs);
}

export interface StopPoint {
  dayMs: number;
  value: number;
}

// The position's resting disaster stop from its open day to today, clipped to the shown days.
// A position opened today starts a day earlier so the segment has two points.
export function stopSegment(
  position: Pick<OpenPosition, "stop_loss" | "opened_at_ms"> | null,
  firstDayMs: number,
  todayMs: number,
): StopPoint[] {
  const value = Number(position?.stop_loss);
  if (position === null || !Number.isFinite(value) || value <= 0) return [];
  const startMs = Math.max(firstDayMs, Math.min(dayStartMs(position.opened_at_ms), todayMs - DAY_MS));
  return [
    { dayMs: startMs, value },
    { dayMs: todayMs, value },
  ];
}
