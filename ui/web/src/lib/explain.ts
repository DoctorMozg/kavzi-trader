import { fmtPlainPct } from "@/lib/format";
import type { TrendState, TrendSymbol } from "@/lib/protocol";

export interface BufferVerdict {
  trades: boolean;
  text: string;
}

const pct = (weight: number): string => fmtPlainPct(weight * 100);

// Mirrors TurnoverBuffer._trade_mask: flatten, sign flip, or drift past the band.
export function bufferVerdict(target: number, held: number, band: number): BufferVerdict {
  if (target === 0 && held === 0) return { trades: false, text: "Nothing held and nothing targeted, so no trade." };
  if (target === 0) return { trades: true, text: `Target is 0 while holding ${pct(held)}, so the position closes.` };
  if (Math.sign(target) !== Math.sign(held)) {
    return { trades: true, text: `Target ${pct(target)} from flat is a new entry, so it trades.` };
  }
  const limit = band * Math.abs(held);
  if (Math.abs(target - held) > limit) {
    return {
      trades: true,
      text: `Target ${pct(target)} differs from held ${pct(held)} by more than ${pct(limit)} (${pct(band)} of held), so it resizes.`,
    };
  }
  return {
    trades: false,
    text: `Target ${pct(target)} is within ${pct(limit)} (${pct(band)} of held ${pct(held)}), so it keeps the position to save fees.`,
  };
}

export function sizeIfLong(state: TrendState, symbol: TrendSymbol): number | null {
  if (symbol.annual_vol === null || symbol.annual_vol === 0) return null;
  const scale = Math.min(state.annual_vol_target / symbol.annual_vol, state.max_leverage);
  return scale / state.symbols.length;
}
