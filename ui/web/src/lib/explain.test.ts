import { describe, expect, it } from "vitest";
import { bufferVerdict, sizeIfLong } from "@/lib/explain";
import type { TrendState, TrendSymbol } from "@/lib/protocol";

const symbol = (over: Partial<TrendSymbol> = {}): TrendSymbol => ({
  symbol: "BTCUSDT",
  signal: 0,
  close: 100,
  entry_level: 120,
  exit_level: 90,
  annual_vol: 0.5,
  target_weight: 0,
  held_weight: 0,
  spike: null,
  halving: null,
  days: [],
  ...over,
});

const state = (symbols: TrendSymbol[]): TrendState => ({
  type: "trend_state",
  ts_ms: 0,
  day: "2026-11-17",
  lookback: 20,
  exit_rule: "mid",
  check_hours: 6,
  next_rebalance_ms: 0,
  symbols,
  annual_vol_target: 0.25,
  max_leverage: 2,
  vol_window: 30,
  buffer_band: 0.2,
  disaster_stop_pct: 0.3,
  vol_spike: { history_hours: 2160, min_history_hours: 720, quantile: 0.99, scale: 0.5 },
});

describe("bufferVerdict", () => {
  it.each([
    [0, 0, false, "Nothing held"],
    [0, 0.05, true, "closes"],
    [0.05, 0, true, "new entry"],
    [0.07, 0.05, true, "resizes"],
    [0.055, 0.05, false, "keeps the position"],
  ])("target %s held %s trades=%s", (target, held, trades, text) => {
    const verdict = bufferVerdict(target, held, 0.2);
    expect(verdict.trades).toBe(trades);
    expect(verdict.text).toContain(text);
  });
});

describe("sizeIfLong", () => {
  it("scales the vol target by realised vol, capped, split over symbols", () => {
    const s = symbol({ annual_vol: 0.5 });
    expect(sizeIfLong(state([s, symbol()]), s)).toBeCloseTo(0.25);
    const calm = symbol({ annual_vol: 0.05 });
    expect(sizeIfLong(state([calm, symbol()]), calm)).toBeCloseTo(1);
  });

  it("is unknown while vol is warming up", () => {
    const s = symbol({ annual_vol: null });
    expect(sizeIfLong(state([s]), s)).toBeNull();
  });
});
