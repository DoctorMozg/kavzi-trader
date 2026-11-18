import { EmptyState } from "@/components/ui/panel";
import { SideBadge } from "@/components/ui/sideBadge";
import { Table, Td, Th } from "@/components/ui/table";
import { fmtDateTime, fmtDuration, fmtPrice, fmtQty, fmtSignedUsd, pnlClass } from "@/lib/format";
import { useStore } from "@/state/store";

export function ClosedTable() {
  const closed = useStore((s) => s.data.closed);
  if (closed.length === 0) return <EmptyState>No closed positions yet</EmptyState>;
  return (
    <Table>
      <thead>
        <tr>
          <Th>Closed</Th>
          <Th>Symbol</Th>
          <Th>Side</Th>
          <Th right hint="Quantity closed">Qty</Th>
          <Th right hint="Average entry fill price">Entry</Th>
          <Th right hint="Exit fill price">Exit</Th>
          <Th right hint="Realised PnL in USDT after fees">PnL</Th>
          <Th hint="What closed it: the daily signal, the disaster stop, or a position-management exit">Reason</Th>
          <Th right hint="Time the position was open">Held</Th>
        </tr>
      </thead>
      <tbody>
        {[...closed].reverse().map((c) => {
          const pnl = Number(c.pnl_usdt);
          return (
            <tr key={c.event_id}>
              <Td className="text-muted-foreground">{fmtDateTime(c.ts_ms)}</Td>
              <Td className="font-medium">{c.symbol}</Td>
              <Td><SideBadge side={c.side} /></Td>
              <Td right>{fmtQty(Number(c.quantity))}</Td>
              <Td right>{fmtPrice(Number(c.entry_price))}</Td>
              <Td right>{fmtPrice(Number(c.exit_price))}</Td>
              <Td right className={pnlClass(pnl)}>{fmtSignedUsd(pnl)}</Td>
              <Td>{c.close_reason}</Td>
              <Td right>{fmtDuration(c.ts_ms - c.opened_at_ms)}</Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
