import { describe, expect, it } from "vitest";
import { nextLiveBar } from "@/lib/liveBar";

const last = { open_time_ms: 1000, open: "10", high: "12", low: "9", close: "11", volume: "1" };

describe("nextLiveBar", () => {
  it("keeps the candle time and open, moving close", () => {
    const { bar } = nextLiveBar(last, 10.5, null);
    expect(bar).toMatchObject({ openTimeMs: 1000, open: 10, close: 10.5, high: 12, low: 9 });
  });

  it("remembers extremes across ticks on the same candle", () => {
    const a = nextLiveBar(last, 14, null);
    const b = nextLiveBar(last, 8, a.extremes);
    const c = nextLiveBar(last, 10, b.extremes);
    expect(c.bar).toMatchObject({ high: 14, low: 8, close: 10 });
  });

  it("drops stale extremes when the last candle changes", () => {
    const a = nextLiveBar(last, 14, null);
    const next = { ...last, open_time_ms: 2000 };
    expect(nextLiveBar(next, 10, a.extremes).bar.high).toBe(12);
  });
});
