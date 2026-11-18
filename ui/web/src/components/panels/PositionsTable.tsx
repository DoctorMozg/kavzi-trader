import { SlTpBar } from "@/components/panels/SlTpBar";
import { EmptyState, Panel, PanelHeader } from "@/components/ui/panel";
import { SideBadge } from "@/components/ui/sideBadge";
import { Table, Td, Th } from "@/components/ui/table";
import { fmtDuration, fmtPct, fmtPrice, fmtQty, fmtSignedUsd, pnlClass } from "@/lib/format";
import type { OpenPosition } from "@/lib/protocol";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/utils";
import { useStore } from "@/state/store";

function PositionRow({ position, now }: { position: OpenPosition; now: number }) {
  const entry = Number(position.entry_price);
  const mark = Number(position.mark_price);
  const stop = Number(position.stop_loss);
  const take = position.take_profit === null ? null : Number(position.take_profit);
  const pnl = Number(position.unrealized_pnl_usdt);
  const notional = Number(position.quantity) * entry;
  return (
    <tr>
      <Td className="font-medium">{position.symbol}</Td>
      <Td><SideBadge side={position.side} /></Td>
      <Td right>{fmtQty(Number(position.quantity))}</Td>
      <Td right>{fmtPrice(entry)}</Td>
      <Td right>{fmtPrice(mark)}</Td>
      <Td right className={cn(pnlClass(pnl))}>
        {fmtSignedUsd(pnl)}
        {notional > 0 && <span className="ml-1 text-xs opacity-80">{fmtPct((pnl / notional) * 100)}</span>}
      </Td>
      <Td>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="text-loss">{fmtPrice(stop)}</span>
          {take === null ? (
            <span>signal exit</span>
          ) : (
            <>
              <SlTpBar stop={stop} take={take} mark={mark} />
              <span className="text-profit">{fmtPrice(take)}</span>
            </>
          )}
        </div>
      </Td>
      <Td right>{position.leverage}x</Td>
      <Td right>{fmtDuration(now - position.opened_at_ms)}</Td>
    </tr>
  );
}

export function PositionsTable() {
  const positions = useStore((s) => s.data.account?.positions);
  const now = useNow();
  return (
    <Panel>
      <PanelHeader title="Open positions" />
      {!positions?.length ? (
        <EmptyState>No open positions</EmptyState>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Symbol</Th>
              <Th hint="LONG profits when price rises. The trend rule only goes long.">Side</Th>
              <Th right hint="Coins held">Qty</Th>
              <Th right hint="Average fill price">Entry</Th>
              <Th right hint="Live mark price used for unrealised PnL">Mark</Th>
              <Th right hint="Unrealised PnL in USDT, and as % of the entry notional">uPnL</Th>
              <Th hint="Stop loss and take profit. Trend positions carry only the disaster stop; the rule exits on a daily close below the channel low ('signal exit').">
                SL / TP
              </Th>
              <Th right hint="Exchange leverage setting. Exposure is set by the target weight, not by this number.">Lev</Th>
              <Th right hint="Time since the position opened">Age</Th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <PositionRow key={p.id} position={p} now={now} />
            ))}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}
