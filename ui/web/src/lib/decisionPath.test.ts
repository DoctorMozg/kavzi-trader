import { describe, expect, it } from "vitest";
import { buildDecisionPath, type PathInput } from "@/lib/decisionPath";
import type { Decision, Trade, TrendState, TrendSymbol } from "@/lib/protocol";

const NOW = 10_000_000;

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

const input = (s: TrendSymbol, over: Partial<PathInput> = {}): PathInput => ({
  state: state([s, symbol({ symbol: "ETHUSDT" })]),
  symbol: s,
  price: 100,
  position: null,
  decisions: [],
  trades: [],
  nowMs: NOW,
  ...over,
});

const values = (path: ReturnType<typeof buildDecisionPath>) =>
  Object.fromEntries(path.steps.map((step) => [step.key, step.value]));

describe("buildDecisionPath", () => {
  it("chains direction × size = target, then buffer, executor and stop", () => {
    const path = buildDecisionPath(input(symbol()));
    expect(path.steps.map((s) => s.via)).toEqual([
      null,
      "×",
      "=",
      "↓ 20.0% turnover buffer",
      "↓ executor",
      "↓ while held",
    ]);
    expect(values(path)).toEqual({
      direction: "FLAT · 0",
      size: "25.0%",
      target: "0.0%",
      held: "0.0%",
      order: "none",
      stop: "off",
    });
  });

  it("says a flat symbol never shorts and what close would enter it", () => {
    const path = buildDecisionPath(input(symbol()));
    expect(path.steps[0]?.text).toContain("never goes SHORT");
    expect(path.next).toContain("above 120.000 (+20.0% from 100.000)");
    expect(path.next).toContain("buys 25.0% of equity");
  });

  it("points a long symbol at its exit, which goes flat rather than short", () => {
    const long = symbol({ signal: 1, target_weight: 0.25, held_weight: 0.25 });
    const path = buildDecisionPath(input(long));
    expect(values(path).direction).toBe("LONG · 1");
    expect(path.next).toContain("below 90.000 (-10.0% from 100.000). That takes it FLAT, never SHORT");
  });

  it("reports the newer of the last trade and the last skipped order", () => {
    const skip = { type: "decision", event_id: "d", ts_ms: NOW - 7_200_000, symbol: "BTCUSDT", stage: "execution" } as Decision;
    const trade = { type: "trade", event_id: "t", ts_ms: NOW - 3_600_000, symbol: "BTCUSDT", side: "LONG", status: "FILLED" } as Trade;
    expect(values(buildDecisionPath(input(symbol(), { decisions: [skip], trades: [trade] }))).order).toBe(
      "LONG filled 1h 0m ago",
    );
    expect(values(buildDecisionPath(input(symbol(), { decisions: [skip] }))).order).toBe("not traded 2h 0m ago");
  });
});
