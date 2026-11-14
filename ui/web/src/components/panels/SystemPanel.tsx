import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";
import { useStore } from "@/state/store";

const STALE_ACCOUNT_S = 5;

function useMessageRate(): number {
  const count = useStore((s) => s.messageCount);
  const [rate, setRate] = useState(0);
  const prev = useRef({ count, at: performance.now() });
  useEffect(() => {
    const id = setInterval(() => {
      const { messageCount } = useStore.getState();
      const at = performance.now();
      setRate(((messageCount - prev.current.count) * 1000) / (at - prev.current.at));
      prev.current = { count: messageCount, at };
    }, 1000);
    return () => clearInterval(id);
  }, []);
  return rate;
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div className={cn("text-lg font-semibold tabular-nums", warn && "text-warn")}>{value}</div>
    </div>
  );
}

export function SystemPanel() {
  const loops = useStore((s) => s.data.account?.running_loops);
  const seq = useStore((s) => s.data.seq);
  const lastAccountMs = useStore((s) => s.lastAccountMs);
  const now = useNow();
  const rate = useMessageRate();
  // `now` ticks on a timer, so it can trail the latest receipt time slightly.
  const accountAgeS =
    lastAccountMs === null ? null : Math.max(0, (now - lastAccountMs) / 1000);

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap gap-1.5">
        {loops?.length ? (
          loops.map((loop) => (
            <Badge key={loop} tone="green">
              {loop}
            </Badge>
          ))
        ) : (
          <span className="text-muted-foreground">No loops reported</span>
        )}
      </div>
      <div className="flex flex-wrap gap-x-10 gap-y-3">
        <Stat
          label="Since last account tick"
          value={accountAgeS === null ? "-" : `${accountAgeS.toFixed(0)} s`}
          warn={accountAgeS !== null && accountAgeS > STALE_ACCOUNT_S}
        />
        <Stat label="Seq" value={seq === null ? "-" : String(seq)} />
        <Stat label="Messages / s" value={rate.toFixed(1)} />
      </div>
    </div>
  );
}
