import type { ClosedPosition, Trade, TrendSymbol } from "@/lib/protocol";

export const DAY_MS = 86_400_000;

export const dayStartMs = (ms: number): number => Math.floor(ms / DAY_MS) * DAY_MS;

// 0 at the exit level, 1 at the entry level, clamped to the channel.
export function channelPosition(price: number, low: number, high: number): number {
  if (high <= low) return 0.5;
  return Math.min(1, Math.max(0, (price - low) / (high - low)));
}

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
