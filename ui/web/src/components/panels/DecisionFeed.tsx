import { useRef, useState } from "react";
import { DecisionItem } from "@/components/panels/DecisionItem";
import { STAGES } from "@/components/panels/decisionStyle";
import { useSymbols } from "@/components/panels/SymbolTabs";
import { EmptyState, Panel, PanelHeader } from "@/components/ui/panel";
import type { Decision, Stage } from "@/lib/protocol";
import { useStore } from "@/state/store";

const SCROLLED_PX = 8;
const selectClass =
  "rounded border bg-muted px-1.5 py-0.5 text-xs text-foreground outline-none focus-visible:ring-1 focus-visible:ring-sky-400";

// Newest-first list that stops accepting new rows while the reader hovers or has scrolled down.
function useFrozenList(live: Decision[]) {
  const [frozen, setFrozen] = useState<Decision[] | null>(null);
  const hovered = useRef(false);
  const scrolled = useRef(false);

  const sync = () => setFrozen((prev) => (hovered.current || scrolled.current ? (prev ?? live) : null));
  const handlers = {
    onMouseEnter: () => {
      hovered.current = true;
      sync();
    },
    onMouseLeave: () => {
      hovered.current = false;
      sync();
    },
    onScroll: (e: React.UIEvent<HTMLElement>) => {
      scrolled.current = e.currentTarget.scrollTop > SCROLLED_PX;
      sync();
    },
  };
  const release = () => {
    hovered.current = false;
    scrolled.current = false;
    setFrozen(null);
  };

  const items = frozen ?? live;
  const newCount = frozen && frozen[0] ? live.indexOf(frozen[0]) : 0;
  return { items, frozen: frozen !== null, newCount: Math.max(newCount, 0), handlers, release };
}

export function DecisionFeed() {
  const decisions = useStore((s) => s.data.decisions);
  const symbols = useSymbols();
  const [symbol, setSymbol] = useState("");
  const [stage, setStage] = useState<Stage | "">("");
  const listRef = useRef<HTMLUListElement>(null);

  const live = decisions
    .filter((d) => (!symbol || d.symbol === symbol) && (!stage || d.stage === stage))
    .reverse();
  const { items, frozen, newCount, handlers, release } = useFrozenList(live);

  const jumpToLatest = () => {
    release();
    listRef.current?.scrollTo({ top: 0 });
  };

  return (
    <Panel className="h-full">
      <PanelHeader title="Decisions">
        <div className="flex gap-2">
          <select
            aria-label="Filter by symbol"
            className={selectClass}
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value);
              release();
            }}
          >
            <option value="">All symbols</option>
            {symbols.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <select
            aria-label="Filter by stage"
            className={selectClass}
            value={stage}
            onChange={(e) => {
              setStage(e.target.value as Stage | "");
              release();
            }}
          >
            <option value="">All stages</option>
            {STAGES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
      </PanelHeader>
      {frozen && newCount > 0 && (
        <button
          type="button"
          onClick={jumpToLatest}
          className="border-b bg-sky-400/10 py-1 text-xs text-sky-300 hover:bg-sky-400/20"
        >
          {newCount} new, jump to latest
        </button>
      )}
      {items.length === 0 ? (
        <EmptyState>No decisions yet</EmptyState>
      ) : (
        <ul ref={listRef} className="min-h-0 flex-1 overflow-y-auto" {...handlers}>
          {items.map((d) => (
            <DecisionItem key={d.event_id} decision={d} />
          ))}
        </ul>
      )}
    </Panel>
  );
}
