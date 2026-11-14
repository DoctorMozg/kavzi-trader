import { Badge } from "@/components/ui/badge";
import { fmtDuration } from "@/lib/format";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";
import { useStore } from "@/state/store";

const STATUS_DOT = {
  live: "bg-profit",
  connecting: "bg-warn animate-pulse",
  reconnecting: "bg-loss animate-pulse",
} as const;

function ConnectionIndicator() {
  const status = useStore((s) => s.status);
  const lastMessageMs = useStore((s) => s.lastMessageMs);
  const now = useNow();
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className={cn("size-2 rounded-full", STATUS_DOT[status])} />
      <span className="capitalize">{status}</span>
      {lastMessageMs !== null && (
        <span className="tabular-nums">{fmtDuration(now - lastMessageMs)} ago</span>
      )}
    </div>
  );
}

function Uptime() {
  const startedMs = useStore((s) => s.data.account?.session_started_at_ms);
  const now = useNow();
  if (startedMs === undefined) return null;
  return (
    <span className="text-xs text-muted-foreground">
      Uptime <span className="tabular-nums text-foreground">{fmtDuration(now - startedMs)}</span>
    </span>
  );
}

export function TopBar() {
  const isPaper = useStore((s) => s.data.account?.is_paper);
  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b bg-card px-4 py-2">
      <h1 className="text-sm font-semibold tracking-tight">KavziTrader</h1>
      {isPaper !== undefined && (
        <Badge tone={isPaper ? "blue" : "amber"}>{isPaper ? "Paper" : "Live"}</Badge>
      )}
      <div className="ml-auto flex flex-wrap items-center gap-x-5 gap-y-1">
        <Uptime />
        <ConnectionIndicator />
      </div>
    </header>
  );
}
