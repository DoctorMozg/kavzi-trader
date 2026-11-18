import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Hint } from "@/components/ui/hint";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";
import { useStore } from "@/state/store";

const STALE_ACCOUNT_S = 5;

const LOOP_HINT: Record<string, string> = {
  ingest: "Streams candles and prices from Binance into the market data cache.",
  order_flow: "Polls funding rate, open interest and liquidation data.",
  reasoning: "Runs the active strategy: in trend mode, the daily Donchian rebalance.",
  execution: "Turns strategy intents into orders, after risk validation.",
  position: "Watches open positions: stops, partial and time exits.",
  ui_snapshot: "Publishes account, candles and gate inputs to this dashboard.",
  external_sentiment: "Fetches Fear & Greed and DVOL for the LLM pipeline.",
};

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

function Stat({ label, hint, value, warn }: { label: string; hint: string; value: string; warn?: boolean }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        <Hint content={hint}>{label}</Hint>
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
            <Hint key={loop} plain content={LOOP_HINT[loop] ?? "Running loop"}>
              <Badge tone="green">{loop}</Badge>
            </Hint>
          ))
        ) : (
          <span className="text-muted-foreground">No loops reported</span>
        )}
      </div>
      <div className="flex flex-wrap gap-x-10 gap-y-3">
        <Stat
          label="Since last account tick"
          hint={`The trader publishes account state every few seconds; over ${STALE_ACCOUNT_S} s turns amber.`}
          value={accountAgeS === null ? "-" : `${accountAgeS.toFixed(0)} s`}
          warn={accountAgeS !== null && accountAgeS > STALE_ACCOUNT_S}
        />
        <Stat label="Seq" hint="Sequence number of the last dashboard event; gaps trigger a resync." value={seq === null ? "-" : String(seq)} />
        <Stat label="Messages / s" hint="WebSocket messages received per second" value={rate.toFixed(1)} />
      </div>
    </div>
  );
}
