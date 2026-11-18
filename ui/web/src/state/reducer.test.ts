import { describe, expect, it } from "vitest";
import type {
  Account,
  Candle,
  ClosedPosition,
  Decision,
  EventMessage,
  SnapshotMessage,
  Trade,
  TrendState,
  UiEventPayload,
} from "@/lib/protocol";
import { applyMessage, CAPS, initialState, type DashboardState } from "@/state/reducer";

const candle = (t: number, close = "1"): Candle => ({
  open_time_ms: t,
  open: "1",
  high: "2",
  low: "0.5",
  close,
  volume: "10",
});

const decision = (n: number): Decision => ({
  type: "decision",
  event_id: `d${n}`,
  ts_ms: n,
  symbol: "BTCUSDT",
  stage: "scout",
  verdict: "SKIP",
  summary: `d${n}`,
  reasoning: null,
  confidence: null,
  latency_ms: null,
});

const trade = (n: number): Trade => ({
  type: "trade",
  event_id: `t${n}`,
  ts_ms: n,
  symbol: "BTCUSDT",
  side: "LONG",
  status: "FILLED",
  confidence: 0.5,
  entry_price: "1",
  quantity: "1",
  stop_loss: null,
  take_profit: null,
  reasoning: "",
});

const closedPos = (n: number, pnl = "1"): ClosedPosition => ({
  type: "position_closed",
  event_id: `c${n}`,
  ts_ms: n,
  symbol: "BTCUSDT",
  side: "LONG",
  quantity: "1",
  entry_price: "1",
  exit_price: "2",
  stop_loss: "0.5",
  take_profit: "3",
  pnl_usdt: pnl,
  close_reason: "TP",
  leverage: 2,
  opened_at_ms: 1,
});

const account = (balance: string): Account => ({
  type: "account",
  ts_ms: 1,
  session_started_at_ms: 1,
  is_paper: true,
  initial_balance_usdt: "1000",
  balance_usdt: balance,
  unrealized_pnl_usdt: "0",
  positions: [],
  prices: {},
  running_loops: [],
});

const snapshot = (seq: number, over: Partial<SnapshotMessage["snapshot"]> = {}): SnapshotMessage => ({
  type: "snapshot",
  seq,
  snapshot: {
    account: null,
    candle_interval: "15m",
    candles: {},
    closed_positions: [],
    decisions: [],
    trades: [],
    trend: null,
    ...over,
  },
});

const trendState = (close: number): TrendState => ({
  type: "trend_state",
  ts_ms: 1,
  day: "2026-11-17",
  lookback: 20,
  next_rebalance_ms: 2,
  symbols: [
    {
      symbol: "BTCUSDT",
      signal: 0,
      close,
      entry_level: 120,
      exit_level: 90,
      annual_vol: 0.5,
      target_weight: 0,
      held_weight: 0,
      days: [{ day_ms: 0, close, upper: null, lower: null, signal: 0 }],
    },
  ],
});

const ev = (seq: number, event: UiEventPayload): EventMessage => ({ type: "event", seq, event });

const candlesEvent = (symbol: string, candles: [Candle, ...Candle[]]): UiEventPayload => ({
  type: "candles",
  ts_ms: 1,
  symbol,
  interval: "15m",
  candles,
});

const seeded = (): DashboardState => applyMessage(initialState, snapshot(10));

describe("snapshot", () => {
  it("replaces all state and sets seq", () => {
    const dirty = applyMessage(seeded(), ev(11, decision(1)));
    const next = applyMessage(
      dirty,
      snapshot(50, {
        account: account("900"),
        decisions: [decision(2)],
        candles: { ETHUSDT: [candle(2), candle(1)] },
      }),
    );
    expect(next.seq).toBe(50);
    expect(next.decisions.map((d) => d.ts_ms)).toEqual([2]);
    expect(next.account?.balance_usdt).toBe("900");
    expect(next.candles["ETHUSDT"]?.map((c) => c.open_time_ms)).toEqual([1, 2]);
    expect(next.candleInterval).toBe("15m");
  });

  it("caps oversized lists to the newest entries", () => {
    const many = Array.from({ length: CAPS.decisions + 5 }, (_, i) => decision(i));
    const next = applyMessage(initialState, snapshot(1, { decisions: many }));
    expect(next.decisions).toHaveLength(CAPS.decisions);
    expect(next.decisions[0]?.ts_ms).toBe(5);
  });
});

describe("events", () => {
  it("advances seq", () => {
    expect(applyMessage(seeded(), ev(11, decision(1))).seq).toBe(11);
  });

  it("appends decisions, trades and closes oldest-first", () => {
    let s = seeded();
    s = applyMessage(s, ev(11, decision(1)));
    s = applyMessage(s, ev(12, decision(2)));
    s = applyMessage(s, ev(13, trade(3)));
    s = applyMessage(s, ev(14, closedPos(4)));
    expect(s.decisions.map((d) => d.ts_ms)).toEqual([1, 2]);
    expect(s.trades).toHaveLength(1);
    expect(s.closed).toHaveLength(1);
  });

  it("replaces the trend state and restores it from a snapshot", () => {
    let s = applyMessage(seeded(), ev(11, trendState(100)));
    s = applyMessage(s, ev(12, trendState(101)));
    expect(s.trend?.symbols[0]?.close).toBe(101);
    const restored = applyMessage(s, snapshot(20, { trend: trendState(99) }));
    expect(restored.trend?.symbols[0]?.close).toBe(99);
    expect(applyMessage(s, snapshot(21)).trend).toBeNull();
  });

  it("replaces the previous account instead of merging", () => {
    const first = { ...account("1000"), prices: { BTCUSDT: "1" }, running_loops: ["a"] };
    let s = applyMessage(seeded(), ev(11, first));
    s = applyMessage(s, ev(12, account("1100")));
    expect(s.account?.balance_usdt).toBe("1100");
    expect(s.account?.prices).toEqual({});
    expect(s.account?.running_loops).toEqual([]);
  });

  it.each([
    ["decisions", CAPS.decisions, decision],
    ["trades", CAPS.trades, trade],
    ["closed", CAPS.closed, closedPos],
  ] as const)("caps %s", (key, cap, make) => {
    let s = seeded();
    for (let i = 0; i < cap + 3; i++) s = applyMessage(s, ev(11 + i, make(i)));
    expect(s[key]).toHaveLength(cap);
    expect(s[key][0]?.ts_ms).toBe(3);
  });
});

describe("candles", () => {
  it("merges by open time, deduping and keeping order", () => {
    let s = applyMessage(seeded(), ev(11, candlesEvent("BTCUSDT", [candle(3), candle(1)])));
    s = applyMessage(s, ev(12, candlesEvent("BTCUSDT", [candle(2), candle(3, "9")])));
    const list = s.candles["BTCUSDT"]!;
    expect(list.map((c) => c.open_time_ms)).toEqual([1, 2, 3]);
    expect(list[2]?.close).toBe("9");
  });

  it("keeps symbols separate and caps each", () => {
    const many = Array.from({ length: CAPS.candles + 4 }, (_, i) => candle(i));
    let s = applyMessage(seeded(), ev(11, candlesEvent("BTCUSDT", [candle(0), ...many])));
    s = applyMessage(s, ev(12, candlesEvent("ETHUSDT", [candle(7)])));
    expect(s.candles["BTCUSDT"]).toHaveLength(CAPS.candles);
    expect(s.candles["BTCUSDT"]?.[0]?.open_time_ms).toBe(4);
    expect(s.candles["ETHUSDT"]).toHaveLength(1);
  });
});
