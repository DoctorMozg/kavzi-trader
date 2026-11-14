import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { STAGE_TONE } from "@/components/panels/decisionStyle";
import { Badge } from "@/components/ui/badge";
import { fmtTime } from "@/lib/format";
import type { Decision } from "@/lib/protocol";
import { cn } from "@/lib/utils";

export function DecisionItem({ decision }: { decision: Decision }) {
  const [open, setOpen] = useState(false);
  const { confidence, latency_ms: latencyMs, reasoning } = decision;
  return (
    <li className="border-b px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="tabular-nums text-muted-foreground">{fmtTime(decision.ts_ms)}</span>
        <span className="font-medium">{decision.symbol}</span>
        <Badge tone={STAGE_TONE[decision.stage]}>{decision.stage}</Badge>
        <span className="font-semibold uppercase tracking-wide">{decision.verdict}</span>
        {latencyMs !== null && (
          <span className="ml-auto tabular-nums text-muted-foreground">{latencyMs} ms</span>
        )}
      </div>
      <p className="mt-1 text-[13px] leading-snug text-foreground/90">{decision.summary}</p>
      {confidence !== null && (
        <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
          <div className="h-1 w-24 overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-sky-400" style={{ width: `${confidence * 100}%` }} />
          </div>
          <span className="tabular-nums">{Math.round(confidence * 100)}%</span>
        </div>
      )}
      {reasoning && (
        <>
          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            <ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} />
            Reasoning
          </button>
          {open && (
            <p className="animate-in fade-in mt-1 whitespace-pre-wrap rounded bg-muted/50 p-2 text-xs leading-relaxed text-muted-foreground">
              {reasoning}
            </p>
          )}
        </>
      )}
    </li>
  );
}
