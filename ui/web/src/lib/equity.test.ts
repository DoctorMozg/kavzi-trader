import { describe, expect, it } from "vitest";
import { equityCurve } from "@/lib/equity";
import type { ClosedPosition } from "@/lib/protocol";

const close = (ts_ms: number, pnl_usdt: string): ClosedPosition => ({
  type: "position_closed",
  event_id: `c${ts_ms}`,
  ts_ms,
  symbol: "BTCUSDT",
  side: "LONG",
  quantity: "1",
  entry_price: "1",
  exit_price: "1",
  stop_loss: "1",
  take_profit: "1",
  pnl_usdt,
  close_reason: "TP",
  leverage: 1,
  opened_at_ms: 0,
});

describe("equityCurve", () => {
  it("starts at zero and accumulates", () => {
    const pts = equityCurve([close(5000, "10"), close(9000, "-4")], 2000);
    expect(pts).toEqual([
      { timeS: 2, value: 0 },
      { timeS: 5, value: 10 },
      { timeS: 9, value: 6 },
    ]);
  });

  it("collapses same-second closes so times stay strictly ascending", () => {
    const pts = equityCurve([close(5100, "1"), close(5900, "2")], null);
    expect(pts.map((p) => p.timeS)).toEqual([4, 5]);
    expect(pts[1]?.value).toBe(3);
  });

  it("is empty without closes", () => {
    expect(equityCurve([], 0)).toEqual([]);
  });
});
