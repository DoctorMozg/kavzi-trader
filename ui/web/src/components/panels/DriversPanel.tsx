import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Hint } from "@/components/ui/hint";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { buildDrivers, type Driver, type Effect } from "@/lib/drivers";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";
import { useStore } from "@/state/store";

const EFFECT: Record<Effect, { tone: BadgeTone; label: string; hint: string }> = {
  decides: { tone: "green", label: "decides", hint: "Opens and closes positions." },
  sizes: { tone: "blue", label: "sizes", hint: "Changes how big a position is, never whether to hold it." },
  guards: { tone: "amber", label: "guards", hint: "Can stop or limit a trade the rule asked for." },
  shadow: { tone: "violet", label: "shadow", hint: "Logged for evaluation only; no effect on trades." },
  unused: { tone: "neutral", label: "unused", hint: "Not part of the active strategy." },
};

function DriverRow({ driver }: { driver: Driver }) {
  const effect = EFFECT[driver.effect];
  return (
    <li className="flex items-baseline gap-2 border-t px-3 py-1.5 text-xs first:border-t-0">
      <Hint content={effect.hint} plain className="w-16 shrink-0">
        <Badge tone={effect.tone}>{effect.label}</Badge>
      </Hint>
      <Hint
        className="shrink-0 font-medium"
        content={
          <div className="space-y-1.5">
            {driver.detail.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        }
      >
        {driver.name}
      </Hint>
      <span
        className={cn(
          "ml-auto truncate text-right tabular-nums text-muted-foreground",
          driver.warn && "text-warn",
          driver.effect === "unused" && "opacity-60",
        )}
      >
        {driver.state}
      </span>
    </li>
  );
}

export function DriversPanel() {
  const trend = useStore((s) => s.data.trend);
  const gateInputs = useStore((s) => s.data.gateInputs);
  const decisions = useStore((s) => s.data.decisions);
  const openPositions = useStore((s) => s.data.account?.positions.length ?? 0);
  const nowMs = useNow();
  const drivers = buildDrivers({ trend, gateInputs, decisions, openPositions, nowMs });
  return (
    <Panel>
      <PanelHeader title="What drives decisions">
        <span className="text-xs text-muted-foreground">hover a name for details</span>
      </PanelHeader>
      <ul>
        {drivers.map((d) => (
          <DriverRow key={d.key} driver={d} />
        ))}
      </ul>
    </Panel>
  );
}
