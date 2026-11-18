import { Badge } from "@/components/ui/badge";
import { EmptyState, Panel, PanelHeader } from "@/components/ui/panel";
import { Table, Td, Th } from "@/components/ui/table";
import { fmtDuration, fmtPct, fmtPlainPct, fmtPrice } from "@/lib/format";
import type { TrendSymbol } from "@/lib/protocol";
import { channelPosition, flipDistance } from "@/lib/trend";
import { useNow } from "@/lib/useNow";
import { useStore } from "@/state/store";

function ChannelBar({ low, high, price }: { low: number; high: number; price: number }) {
  return (
    <div className="relative h-1.5 w-28 rounded-full bg-gradient-to-r from-loss/50 via-muted to-profit/50">
      <span
        className="absolute top-1/2 h-3 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded bg-foreground"
        style={{ left: `${channelPosition(price, low, high) * 100}%` }}
      />
    </div>
  );
}

function TrendRow({ symbol, price }: { symbol: TrendSymbol; price: number }) {
  const isLong = symbol.signal > 0;
  const flip = flipDistance(symbol, price);
  return (
    <tr>
      <Td className="font-medium">{symbol.symbol}</Td>
      <Td>
        <Badge tone={isLong ? "green" : "neutral"}>{isLong ? "LONG" : "FLAT"}</Badge>
      </Td>
      <Td right>{fmtPrice(price)}</Td>
      <Td>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-loss">{fmtPrice(symbol.exit_level)}</span>
          <ChannelBar low={symbol.exit_level} high={symbol.entry_level} price={price} />
          <span className="text-profit">{fmtPrice(symbol.entry_level)}</span>
        </div>
      </Td>
      <Td right className={flip.target === "entry" ? "text-profit" : "text-loss"}>
        {fmtPct(flip.pct)} <span className="text-xs text-muted-foreground">to {flip.target}</span>
      </Td>
      <Td right>{symbol.annual_vol === null ? "-" : fmtPlainPct(symbol.annual_vol * 100)}</Td>
      <Td right>{fmtPlainPct(symbol.target_weight * 100)}</Td>
      <Td right>{fmtPlainPct(symbol.held_weight * 100)}</Td>
    </tr>
  );
}

export function TrendPanel() {
  const trend = useStore((s) => s.data.trend);
  const prices = useStore((s) => s.data.account?.prices);
  const now = useNow();
  return (
    <Panel>
      <PanelHeader title="Trend model">
        {trend && (
          <span className="text-xs text-muted-foreground">
            {trend.lookback}d Donchian, long/flat · state of {trend.day} close · next rebalance in{" "}
            <span className="tabular-nums text-foreground">{fmtDuration(trend.next_rebalance_ms - now)}</span>
          </span>
        )}
      </PanelHeader>
      {!trend ? (
        <EmptyState>Waiting for the trend rule's first report</EmptyState>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Symbol</Th>
              <Th>State</Th>
              <Th right>Live</Th>
              <Th title="Exit level, live price, entry level">Channel</Th>
              <Th right title="Live price vs the level a daily close must break; only the 00:00 UTC close counts">
                Flip
              </Th>
              <Th right>Vol</Th>
              <Th right title="Raw target weight, before the turnover buffer">Target</Th>
              <Th right title="Weight held after the turnover buffer">Held</Th>
            </tr>
          </thead>
          <tbody>
            {trend.symbols.map((s) => {
              const live = Number(prices?.[s.symbol]);
              return <TrendRow key={s.symbol} symbol={s} price={Number.isFinite(live) && live > 0 ? live : s.close} />;
            })}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}
