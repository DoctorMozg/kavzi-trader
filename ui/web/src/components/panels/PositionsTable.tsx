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
  const take = Number(position.take_profit);
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
          <SlTpBar stop={stop} take={take} mark={mark} />
          <span className="text-profit">{fmtPrice(take)}</span>
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
              <Th>Side</Th>
              <Th right>Qty</Th>
              <Th right>Entry</Th>
              <Th right>Mark</Th>
              <Th right>uPnL</Th>
              <Th>SL / TP</Th>
              <Th right>Lev</Th>
              <Th right>Age</Th>
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
