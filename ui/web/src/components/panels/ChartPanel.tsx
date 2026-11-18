import { useState } from "react";
import { DailyChart } from "@/components/panels/DailyChart";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { PriceChart } from "@/components/panels/PriceChart";
import { SymbolTabs, useSelectedSymbol, useSymbols } from "@/components/panels/SymbolTabs";
import { fmtPrice } from "@/lib/format";
import { useStore } from "@/state/store";

type ChartView = "daily" | "intraday";

function ViewToggle({ value, onChange }: { value: ChartView; onChange: (view: ChartView) => void }) {
  const interval = useStore((s) => s.data.candleInterval) ?? "intraday";
  const views: [ChartView, string][] = [
    ["daily", "1D trend"],
    ["intraday", interval],
  ];
  return (
    <div className="flex rounded border text-xs">
      {views.map(([view, label]) => (
        <button
          key={view}
          type="button"
          onClick={() => onChange(view)}
          className={
            view === value
              ? "bg-muted px-2 py-0.5 text-foreground"
              : "px-2 py-0.5 text-muted-foreground hover:text-foreground"
          }
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function LastPrice({ symbol }: { symbol: string }) {
  const price = useStore((s) => s.data.account?.prices[symbol]);
  return (
    <div className="flex items-baseline gap-3 text-xs text-muted-foreground">
      {price !== undefined && (
        <span className="text-sm font-semibold tabular-nums text-foreground">
          {fmtPrice(Number(price))}
        </span>
      )}
    </div>
  );
}

export function ChartPanel() {
  const symbols = useSymbols();
  const symbol = useSelectedSymbol();
  const selectSymbol = useStore((s) => s.selectSymbol);
  const [view, setView] = useState<ChartView>("daily");

  return (
    <Panel>
      <PanelHeader title="Chart">
        <SymbolTabs symbols={symbols} value={symbol} onChange={selectSymbol} />
        <div className="flex items-center gap-3">
          <ViewToggle value={view} onChange={setView} />
          {symbol && <LastPrice symbol={symbol} />}
        </div>
      </PanelHeader>
      <div className="h-[clamp(320px,50vh,760px)]">
        {symbol ? (
          view === "daily" ? (
            <DailyChart symbol={symbol} />
          ) : (
            <PriceChart symbol={symbol} />
          )
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            Waiting for market data
          </div>
        )}
      </div>
    </Panel>
  );
}
