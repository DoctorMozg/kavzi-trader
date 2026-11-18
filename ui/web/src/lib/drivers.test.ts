import { describe, expect, it } from "vitest";
import { buildDrivers, type DriverInputs, STALE_NEWS_MS } from "@/lib/drivers";
import type { Decision, GateInputs, TrendState, TrendSymbol } from "@/lib/protocol";

const NOW = 1_000_000_000;

const symbol = (name: string, signal: number, vol: number | null, held = 0): TrendSymbol => ({
  symbol: name,
  signal,
  close: 100,
  entry_level: 120,
  exit_level: 90,
  annual_vol: vol,
  target_weight: signal > 0 ? 0.1 : 0,
  held_weight: held,
  days: [],
});

const trend: TrendState = {
  type: "trend_state",
  ts_ms: 0,
  day: "2026-11-17",
  lookback: 20,
  next_rebalance_ms: 0,
  symbols: [symbol("BTCUSDT", 1, 0.5, 0.1), symbol("ETHUSDT", 0, 1.0), symbol("SOLUSDT", 1, null)],
  annual_vol_target: 0.25,
  max_leverage: 2,
  vol_window: 30,
  buffer_band: 0.2,
  disaster_stop_pct: 0.3,
};

const gate = (newestAgoMs: number | null): GateInputs => ({
  type: "gate_inputs",
  ts_ms: 0,
  model_id: "claude-sonnet-5-5",
  samples: 3,
  prompt_sha: "abc",
  window_h: 72,
  lag_h: 2,
  headlines: 40,
  newest_ms: newestAgoMs === null ? null : NOW - newestAgoMs,
  coin_headlines: { ETH: 2, BTC: 9 },
});

const decision = (stage: Decision["stage"], symbolName: string, verdict: string): Decision => ({
  type: "decision",
  event_id: `${stage}-${symbolName}`,
  ts_ms: NOW - 3_600_000,
  symbol: symbolName,
  stage,
  verdict,
  summary: "",
  confidence: null,
  reasoning: null,
  latency_ms: null,
});

const inputs = (over: Partial<DriverInputs> = {}): DriverInputs => ({
  trend,
  gateInputs: gate(3_600_000),
  decisions: [],
  openPositions: 1,
  nowMs: NOW,
  ...over,
});

const byKey = (over: Partial<DriverInputs> = {}) =>
  Object.fromEntries(buildDrivers(inputs(over)).map((d) => [d.key, d]));

describe("buildDrivers", () => {
  it("lists every input, with only the Donchian rule deciding", () => {
    const drivers = buildDrivers(inputs());
    expect(drivers.filter((d) => d.effect === "decides").map((d) => d.key)).toEqual(["signal"]);
    expect(drivers.find((d) => d.key === "sentiment")?.effect).toBe("unused");
    expect(drivers.filter((d) => d.effect === "shadow").map((d) => d.key)).toEqual(["news", "gate"]);
  });

  it("summarises the rule state, sizing range and buffer drift", () => {
    const d = byKey();
    expect(d.signal?.state).toBe("2 long, 1 flat (2026-11-17 close)");
    expect(d.vol?.state).toBe("vol 50.0%–100.0%, size if long 8.3%–16.7%");
    expect(d.buffer?.state).toBe("20.0% band, 1 of 3 held off target");
  });

  it("flags stale or missing news and orders coins by count", () => {
    expect(byKey().news?.warn).toBe(false);
    expect(byKey({ gateInputs: gate(STALE_NEWS_MS + 1) }).news?.warn).toBe(true);
    expect(byKey({ gateInputs: gate(null) }).news?.warn).toBe(true);
    expect(byKey().news?.detail[1]).toContain("BTC 9, ETH 2");
  });

  it("shows the latest gate review and execution skip", () => {
    const decisions = [decision("gate", "SOLUSDT", "KEEP"), decision("execution", "ETHUSDT", "NOT TRADED")];
    const d = byKey({ decisions });
    expect(d.gate?.state).toBe("SOLUSDT KEEP 1h 0m ago");
    expect(d.execution?.state).toBe("ETHUSDT not traded 1h 0m ago");
    expect(byKey().gate?.state).toBe("Idle until a symbol turns LONG");
  });
});
