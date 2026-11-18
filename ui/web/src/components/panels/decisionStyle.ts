import type { BadgeTone } from "@/components/ui/badge";
import type { Stage } from "@/lib/protocol";

export const STAGES: Stage[] = ["trend", "gate", "scout", "analyst", "trader", "filter", "position"];

export const STAGE_TONE: Record<Stage, BadgeTone> = {
  scout: "blue",
  analyst: "violet",
  trader: "amber",
  filter: "neutral",
  position: "cyan",
  trend: "green",
  gate: "violet",
};
