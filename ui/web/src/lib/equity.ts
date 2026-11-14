import type { ClosedPosition } from "@/lib/protocol";

export interface EquityPoint {
  timeS: number;
  value: number;
}

// Chart times must be strictly ascending, so closes within one second collapse to the last value.
export function equityCurve(closed: ClosedPosition[], startMs: number | null): EquityPoint[] {
  if (closed.length === 0) return [];
  const sorted = [...closed].sort((a, b) => a.ts_ms - b.ts_ms);
  const firstS = Math.floor(sorted[0]!.ts_ms / 1000);
  const startS = Math.min(startMs === null ? firstS - 1 : Math.floor(startMs / 1000), firstS - 1);
  const points = new Map<number, number>([[startS, 0]]);
  let total = 0;
  for (const c of sorted) {
    total += Number(c.pnl_usdt);
    points.set(Math.floor(c.ts_ms / 1000), total);
  }
  return [...points].map(([timeS, value]) => ({ timeS, value }));
}
