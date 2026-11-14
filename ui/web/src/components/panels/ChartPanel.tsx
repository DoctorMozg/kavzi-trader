import { useState } from "react";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { PriceChart } from "@/components/panels/PriceChart";
import { SymbolTabs, useSymbols } from "@/components/panels/SymbolTabs";
import { fmtPrice } from "@/lib/format";
import { useStore } from "@/state/store";

function LastPrice({ symbol }: { symbol: string }) {
  const interval = useStore((s) => s.data.candleInterval);
  const price = useStore((s) => s.data.account?.prices[symbol]);
  return (
    <div className="flex items-baseline gap-3 text-xs text-muted-foreground">
      {interval && <span className="uppercase">{interval}</span>}
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
  const [selected, setSelected] = useState("");
  const symbol = symbols.includes(selected) ? selected : (symbols[0] ?? "");

  return (
    <Panel>
      <PanelHeader title="Chart">
        <SymbolTabs symbols={symbols} value={symbol} onChange={setSelected} />
        {symbol && <LastPrice symbol={symbol} />}
      </PanelHeader>
      <div className="h-[clamp(320px,50vh,760px)]">
        {symbol ? (
          <PriceChart symbol={symbol} />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            Waiting for market data
          </div>
        )}
      </div>
    </Panel>
  );
}
