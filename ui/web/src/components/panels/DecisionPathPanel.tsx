import { useSelectedSymbol } from "@/components/panels/SymbolTabs";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Panel, PanelHeader } from "@/components/ui/panel";
import { buildDecisionPath, type PathStep } from "@/lib/decisionPath";
import { checkSchedule } from "@/lib/trend";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";
import { useStore } from "@/state/store";

function Step({ step, index }: { step: PathStep; index: number }) {
  const isDirection = step.key === "direction";
  return (
    <li>
      {step.via && (
        <div
          className={cn(
            "py-0.5 pl-7 text-muted-foreground",
            step.via.length === 1 ? "text-base font-semibold leading-none text-foreground" : "text-[11px]",
          )}
        >
          {step.via}
        </div>
      )}
      <div className="grid grid-cols-[1.25rem_6.5rem_1fr] items-baseline gap-x-2">
        <span className="flex size-5 items-center justify-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground">
          {index + 1}
        </span>
        <span className="text-xs font-medium">{step.label}</span>
        <span
          className={cn(
            "text-sm font-semibold tabular-nums",
            isDirection && (step.value.startsWith("LONG") ? "text-profit" : "text-muted-foreground"),
          )}
        >
          {step.value}
        </span>
        <p className="col-start-3 text-xs leading-snug text-muted-foreground">{step.text}</p>
      </div>
    </li>
  );
}

export function DecisionPathPanel() {
  const symbolName = useSelectedSymbol();
  const trend = useStore((s) => s.data.trend);
  const account = useStore((s) => s.data.account);
  const decisions = useStore((s) => s.data.decisions);
  const trades = useStore((s) => s.data.trades);
  const nowMs = useNow();
  const symbol = trend?.symbols.find((s) => s.symbol === symbolName);
  const live = Number(account?.prices[symbolName]);
  return (
    <Panel>
      <PanelHeader title={`How ${symbolName || "a symbol"} is decided`}>
        <span className="text-xs text-muted-foreground">pick a row in Trend model</span>
      </PanelHeader>
      {!trend || !symbol ? (
        <EmptyState>Waiting for the trend rule's first report</EmptyState>
      ) : (
        (() => {
          const path = buildDecisionPath({
            state: trend,
            symbol,
            price: Number.isFinite(live) && live > 0 ? live : symbol.close,
            position: account?.positions.find((p) => p.symbol === symbolName) ?? null,
            decisions,
            trades,
            nowMs,
          });
          return (
            <div className="space-y-3 p-3">
              <ol className="space-y-1">
                {path.steps.map((step, i) => (
                  <Step key={step.key} step={step} index={i} />
                ))}
              </ol>
              <div className="rounded-md border border-sky-400/30 bg-sky-400/5 p-2 text-xs leading-snug">
                <Badge tone="blue" className="mr-1.5">
                  next change
                </Badge>
                {path.next}
              </div>
              <p className="text-[11px] text-muted-foreground">
                Steps 1 to 3 run {checkSchedule(trend)}. Only step 1 can open or close a position;
                steps 2 to 6 decide how much and how safely.
              </p>
            </div>
          );
        })()
      )}
    </Panel>
  );
}
