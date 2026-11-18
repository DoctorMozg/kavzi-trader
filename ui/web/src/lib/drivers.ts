import { sizeIfLong } from "@/lib/explain";
import { fmtDuration, fmtPlainPct } from "@/lib/format";
import type { Decision, GateInputs, TrendState } from "@/lib/protocol";

export type Effect = "decides" | "sizes" | "guards" | "shadow" | "unused";

export interface Driver {
  key: string;
  name: string;
  effect: Effect;
  state: string;
  warn: boolean;
  detail: string[];
}

export interface DriverInputs {
  trend: TrendState | null;
  gateInputs: GateInputs | null;
  decisions: Decision[];
  openPositions: number;
  nowMs: number;
}

// The collector runs hourly, so a gap past a few hours means it stopped.
export const STALE_NEWS_MS = 6 * 3_600_000;

const pct = (weight: number): string => fmtPlainPct(weight * 100);

function latest(decisions: Decision[], stage: Decision["stage"]): Decision | undefined {
  for (let i = decisions.length - 1; i >= 0; i--) {
    if (decisions[i]?.stage === stage) return decisions[i];
  }
  return undefined;
}

function signalDriver(trend: TrendState | null): Driver {
  const longs = trend?.symbols.filter((s) => s.signal > 0).length ?? 0;
  const n = trend?.lookback ?? 20;
  return {
    key: "signal",
    name: "Daily closes · Donchian rule",
    effect: "decides",
    state: trend ? `${longs} long, ${trend.symbols.length - longs} flat (${trend.day} close)` : "Waiting for first report",
    warn: false,
    detail: [
      `The only input that opens or closes a position. A daily close above the previous ${n}-day high turns a symbol LONG; a close below the previous ${n}-day low turns it FLAT. Between the two it keeps its state.`,
      "It runs once a day at 00:01 UTC on the closed daily bar, so intraday moves never trade on their own.",
    ],
  };
}

function volDriver(trend: TrendState | null): Driver {
  const vols = trend?.symbols.flatMap((s) => (s.annual_vol === null ? [] : [s.annual_vol])) ?? [];
  const sizes = trend?.symbols.flatMap((s) => {
    const w = sizeIfLong(trend, s);
    return w === null ? [] : [w];
  }) ?? [];
  const range = (xs: number[]): string => `${pct(Math.min(...xs))}–${pct(Math.max(...xs))}`;
  return {
    key: "vol",
    name: "Realised volatility",
    effect: "sizes",
    state: vols.length ? `vol ${range(vols)}, size if long ${range(sizes)}` : "Warming up",
    warn: false,
    detail: [
      trend
        ? `Sets how big a LONG is, never whether to hold one: weight = min(${pct(trend.annual_vol_target)} ÷ vol, ${trend.max_leverage}×) ÷ ${trend.symbols.length} symbols, with vol from the last ${trend.vol_window} daily returns.`
        : "Sets how big a LONG is, never whether to hold one.",
      "Calmer coins get bigger weights, so each position adds roughly the same risk to the book.",
    ],
  };
}

function bufferDriver(trend: TrendState | null): Driver {
  const drift = trend?.symbols.filter((s) => s.target_weight !== s.held_weight).length ?? 0;
  return {
    key: "buffer",
    name: "Turnover buffer",
    effect: "guards",
    state: trend ? `${pct(trend.buffer_band)} band, ${drift} of ${trend.symbols.length} held off target` : "-",
    warn: false,
    detail: [
      "Decides whether a new target is worth trading. Entries, exits and sign flips always trade; a resize trades only when the target moves more than the band times the held weight.",
      "Small daily vol wiggles would otherwise pay fees every day for no change in exposure.",
    ],
  };
}

function stopDriver(trend: TrendState | null, openPositions: number): Driver {
  return {
    key: "stop",
    name: "Disaster stop",
    effect: "guards",
    state: trend ? `${pct(trend.disaster_stop_pct)} below fill, ${openPositions} armed` : "-",
    warn: false,
    detail: [
      "A resting stop order placed with every entry. It only fires on a crash between daily closes; normal exits come from the Donchian low.",
    ],
  };
}

function executionDriver(decisions: Decision[], nowMs: number): Driver {
  const last = latest(decisions, "execution");
  return {
    key: "execution",
    name: "Execution checks",
    effect: "guards",
    state: last ? `${last.symbol} not traded ${fmtDuration(nowMs - last.ts_ms)} ago` : "No skipped orders",
    warn: false,
    detail: [
      "Turns a target weight into a quantity at the live price and equity. It skips the trade when the change rounds to nothing or is below the minimum notional (within_tolerance), and rejects it when risk validation fails: exposure, leverage, stop distance or an expired intent (1 h).",
      "Skipped and rejected targets show in the feed as EXECUTION with the reason.",
    ],
  };
}

function newsDriver(gate: GateInputs | null, nowMs: number): Driver {
  if (!gate) {
    return {
      key: "news",
      name: "News headlines",
      effect: "shadow",
      state: "Gate off or no report yet",
      warn: false,
      detail: ["Headlines feed only the shadow gate; the trend rule never reads them."],
    };
  }
  const age = gate.newest_ms === null ? null : nowMs - gate.newest_ms;
  const coins = Object.entries(gate.coin_headlines)
    .sort((a, b) => b[1] - a[1])
    .map(([coin, count]) => `${coin} ${count}`)
    .join(", ");
  return {
    key: "news",
    name: "News headlines",
    effect: "shadow",
    state: `${gate.headlines} in ${gate.window_h} h${age === null ? ", none yet" : `, newest ${fmtDuration(age)} ago`}`,
    warn: age === null || age > STALE_NEWS_MS,
    detail: [
      `Headlines published in the last ${gate.window_h} h that the gate could have seen (${gate.lag_h} h publication lag). Collected hourly from five outlet RSS feeds into data/news.`,
      coins ? `Tagged by coin: ${coins}. Untagged headlines count as market-wide news.` : "No headline mentions a traded coin.",
      "They feed only the shadow gate below; the trend rule never reads them.",
    ],
  };
}

function gateDriver(gate: GateInputs | null, decisions: Decision[], nowMs: number): Driver {
  const last = latest(decisions, "gate");
  return {
    key: "gate",
    name: "Shadow LLM news gate",
    effect: "shadow",
    state: last
      ? `${last.symbol} ${last.verdict} ${fmtDuration(nowMs - last.ts_ms)} ago`
      : "Idle until a symbol turns LONG",
    warn: false,
    detail: [
      gate
        ? `On each new LONG entry, ${gate.model_id} reads the headline window ${gate.samples}× and votes KEEP or VETO; a majority VETO marks the entry as vetoed. Prompt ${gate.prompt_sha}.`
        : "On each new LONG entry, an LLM reads recent headlines and votes KEEP or VETO.",
      "Logged to results/trend_gate/shadow.jsonl only. It never blocks, delays or resizes a trade. Its value is scored after 2027-11-17 once 40+ entries are logged (preregistration Part B).",
    ],
  };
}

const sentimentDriver: Driver = {
  key: "sentiment",
  name: "Fear & Greed, DVOL",
  effect: "unused",
  state: "Not fetched in trend mode",
  warn: false,
  detail: [
    "Market sentiment feeds only the LLM pipeline strategy (Analyst and Trader prompts). The trend strategy neither fetches nor reads it.",
  ],
};

export function buildDrivers(inputs: DriverInputs): Driver[] {
  const { trend, gateInputs, decisions, openPositions, nowMs } = inputs;
  return [
    signalDriver(trend),
    volDriver(trend),
    bufferDriver(trend),
    stopDriver(trend, openPositions),
    executionDriver(decisions, nowMs),
    newsDriver(gateInputs, nowMs),
    gateDriver(gateInputs, decisions, nowMs),
    sentimentDriver,
  ];
}
