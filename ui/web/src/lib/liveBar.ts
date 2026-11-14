import type { Candle } from "@/lib/protocol";

export interface LiveExtremes {
  openTimeMs: number;
  high: number;
  low: number;
}

export interface LiveBar {
  openTimeMs: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

// Only ever reshapes the last known candle; a new bar appears when the server sends one.
export function nextLiveBar(
  last: Candle,
  price: number,
  prev: LiveExtremes | null,
): { bar: LiveBar; extremes: LiveExtremes } {
  const base =
    prev?.openTimeMs === last.open_time_ms
      ? prev
      : { openTimeMs: last.open_time_ms, high: Number(last.high), low: Number(last.low) };
  const extremes = {
    openTimeMs: base.openTimeMs,
    high: Math.max(base.high, price),
    low: Math.min(base.low, price),
  };
  const bar = {
    openTimeMs: last.open_time_ms,
    open: Number(last.open),
    high: extremes.high,
    low: extremes.low,
    close: price,
  };
  return { bar, extremes };
}
