import { describe, expect, it } from "vitest";
import type { ClosedPosition, Trade, TrendSymbol } from "@/lib/protocol";
import { channelPosition, DAY_MS, exitName, flipDistance, fmtUtcHour, spikeRatio, tradeMarks } from "@/lib/trend";

const symbol = (signal: number): TrendSymbol => ({
  symbol: "BTCUSDT",
  signal,
  close: 100,
  entry_level: 120,
  exit_level: 80,
  annual_vol: 0.5,
  target_weight: 0,
  held_weight: 0,
  spike: null,
  halving: null,
  days: [],
});

const trade = (ts: number, side: Trade["side"], status = "FILLED"): Trade => ({
  type: "trade",
  event_id: `t${ts}`,
  ts_ms: ts,
  symbol: "BTCUSDT",
  side,
  status,
  confidence: null,
  entry_price: "1",
  quantity: "1",
  stop_loss: null,
  take_profit: null,
  reasoning: "",
});

const close = (ts: number): ClosedPosition => ({
  type: "position_closed",
  event_id: `c${ts}`,
  ts_ms: ts,
  symbol: "BTCUSDT",
  side: "LONG",
  quantity: "1",
  entry_price: "1",
  exit_price: "1",
  stop_loss: "0.7",
  take_profit: null,
  pnl_usdt: "0",
  close_reason: "rebalance",
  leverage: 1,
  opened_at_ms: 0,
});

describe("channelPosition", () => {
  it("maps exit to 0 and entry to 1, clamping outside", () => {
    expect(channelPosition(90, 80, 120)).toBe(0.25);
    expect(channelPosition(130, 80, 120)).toBe(1);
    expect(channelPosition(70, 80, 120)).toBe(0);
    expect(channelPosition(80, 80, 80)).toBe(0.5);
  });
});

describe("flipDistance", () => {
  it("measures to the entry level when flat and to the exit level when long", () => {
    const flat = flipDistance(symbol(0), 100);
    const long = flipDistance(symbol(1), 100);
    expect(flat.target).toBe("entry");
    expect(flat.pct).toBeCloseTo(20);
    expect(long.target).toBe("exit");
    expect(long.pct).toBeCloseTo(-20);
  });
});

describe("tradeMarks", () => {
  it("marks filled longs and closes on their UTC day, oldest first", () => {
    const marks = tradeMarks(
      "BTCUSDT",
      [trade(3 * DAY_MS + 60_000, "LONG"), trade(DAY_MS, "LONG", "REJECTED"), trade(DAY_MS, "CLOSE")],
      [close(5 * DAY_MS + 60_000)],
    );
    expect(marks).toEqual([
      { dayMs: 3 * DAY_MS, kind: "entry", text: "Long" },
      { dayMs: 5 * DAY_MS, kind: "exit", text: "rebalance" },
    ]);
  });

  it("ignores other symbols", () => {
    expect(tradeMarks("ETHUSDT", [trade(DAY_MS, "LONG")], [close(DAY_MS)])).toEqual([]);
  });
});

describe("exit rule and spike helpers", () => {
  it("names the exit level by rule", () => {
    expect(exitName({ exit_rule: "mid", lookback: 20 })).toBe("20-day midpoint");
    expect(exitName({ exit_rule: "low", lookback: 20 })).toBe("20-day low");
  });

  it("gives the variance as a multiple of the threshold, or null without one", () => {
    expect(spikeRatio({ hour_ms: 0, rv: 3, threshold: 2 })).toBe(1.5);
    expect(spikeRatio({ hour_ms: 0, rv: 3, threshold: null })).toBeNull();
    expect(spikeRatio(null)).toBeNull();
  });

  it("formats the UTC hour", () => {
    expect(fmtUtcHour(DAY_MS + 9 * 3_600_000)).toBe("09:00 UTC");
  });
});
