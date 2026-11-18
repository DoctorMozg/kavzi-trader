import { describe, expect, it } from "vitest";
import { bufferVerdict, sizeIfLong, trendSteps } from "@/lib/explain";
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
  days: [],
  ...over,
});

const state = (symbols: TrendSymbol[]): TrendState => ({
  type: "trend_state",
  ts_ms: 0,
  day: "2026-11-17",
  lookback: 20,
  next_rebalance_ms: 0,
  symbols,
  annual_vol_target: 0.25,
  max_leverage: 2,
  vol_window: 30,
  buffer_band: 0.2,
  disaster_stop_pct: 0.3,
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

describe("trendSteps", () => {
  it("explains a flat symbol up to the level that would flip it", () => {
    const s = symbol();
    const steps = trendSteps(state([s, symbol()]), s, 100);
    expect(steps.map((x) => x.label)).toEqual([
      "Signal",
      "Volatility",
      "Size if long",
      "Target",
      "Buffer",
      "Next flip",
    ]);
    expect(steps.at(-1)?.text).toContain("above 120.000 (+20.0% from 100.000) turns it LONG");
  });

  it("points a long symbol at its exit level", () => {
    const s = symbol({ signal: 1, target_weight: 0.25, held_weight: 0.25 });
    const steps = trendSteps(state([s]), s, 100);
    expect(steps.at(-1)?.text).toContain("below 90.000 (-10.0% from 100.000) turns it FLAT");
  });
});
