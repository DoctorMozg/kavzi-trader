import { EmptyState } from "@/components/ui/panel";
import { SideBadge } from "@/components/ui/sideBadge";
import { Table, Td, Th } from "@/components/ui/table";
import { fmtDateTime, fmtPrice, fmtQty } from "@/lib/format";
import { useStore } from "@/state/store";

const price = (value: string | null): string => (value === null ? "-" : fmtPrice(Number(value)));

export function TradesTable() {
  const trades = useStore((s) => s.data.trades);
  if (trades.length === 0) return <EmptyState>No trades yet</EmptyState>;
  return (
    <Table>
      <thead>
        <tr>
          <Th>Time</Th>
          <Th>Symbol</Th>
          <Th>Side</Th>
          <Th>Status</Th>
          <Th right>Qty</Th>
          <Th right>Entry</Th>
          <Th right>SL</Th>
          <Th right>TP</Th>
          <Th right>Conf</Th>
        </tr>
      </thead>
      <tbody>
        {[...trades].reverse().map((t) => (
          <tr key={t.event_id}>
            <Td className="text-muted-foreground">{fmtDateTime(t.ts_ms)}</Td>
            <Td className="font-medium">{t.symbol}</Td>
            <Td><SideBadge side={t.side} /></Td>
            <Td>{t.status}</Td>
            <Td right>{t.quantity === null ? "-" : fmtQty(Number(t.quantity))}</Td>
            <Td right>{price(t.entry_price)}</Td>
            <Td right>{price(t.stop_loss)}</Td>
            <Td right>{price(t.take_profit)}</Td>
            <Td right>{t.confidence === null ? "-" : `${Math.round(t.confidence * 100)}%`}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
