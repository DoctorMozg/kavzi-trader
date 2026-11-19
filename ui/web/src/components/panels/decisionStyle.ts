import type { BadgeTone } from "@/components/ui/badge";
import type { Stage } from "@/lib/protocol";

export const STAGES: Stage[] = ["trend", "gate", "execution", "scout", "analyst", "trader", "filter", "position"];

export const STAGE_TONE: Record<Stage, BadgeTone> = {
  scout: "blue",
  analyst: "violet",
  trader: "amber",
  filter: "neutral",
  position: "cyan",
  trend: "green",
  gate: "violet",
  execution: "amber",
};

export const STAGE_HINT: Record<Stage, string> = {
  trend: "Daily Donchian rule result for one symbol, or an hourly vol-spike halving (HALVE). This is the decision: it sets the target weight the executor trades.",
  gate: "Shadow LLM news check on a new LONG entry. Logged for later scoring; it never changes the trade.",
  execution: "A target change the executor did not trade, with the reason (too small to matter, or a risk check failed).",
  scout: "LLM pipeline only: deterministic filter that decides whether a candle is worth sending to the Analyst.",
  analyst: "LLM pipeline only: the Analyst model validates the setup before the Trader sees it.",
  trader: "LLM pipeline only: the Trader model proposes a trade with entry, stop and take-profit.",
  filter: "LLM pipeline only: pre-trade filters (liquidity, funding, correlation, cooldowns) that can block a signal.",
  position: "Position management action: a partial exit, time exit or stop change on an open position.",
};
