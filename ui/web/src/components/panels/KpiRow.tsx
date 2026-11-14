import { fmtPct, fmtPlainPct, fmtSignedUsd, fmtUsd, pnlClass } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useStore } from "@/state/store";

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="min-w-0 rounded-lg border bg-card px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div className={cn("truncate text-lg font-semibold tabular-nums", tone)}>{value}</div>
      <div className="h-4 text-xs tabular-nums text-muted-foreground">{sub}</div>
    </div>
  );
}

export function KpiRow() {
  const account = useStore((s) => s.data.account);
  const closed = useStore((s) => s.data.closed);

  const balance = account ? Number(account.balance_usdt) : null;
  const sessionPnl = account && balance !== null ? balance - Number(account.initial_balance_usdt) : null;
  const initial = account ? Number(account.initial_balance_usdt) : 0;
  const unrealized = account ? Number(account.unrealized_pnl_usdt) : null;
  const realized = closed.reduce((sum, c) => sum + Number(c.pnl_usdt), 0);
  const wins = closed.filter((c) => Number(c.pnl_usdt) > 0).length;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Kpi label="Balance" value={balance === null ? "-" : fmtUsd(balance)} sub="USDT" />
      <Kpi
        label="Session PnL"
        value={sessionPnl === null ? "-" : fmtSignedUsd(sessionPnl)}
        sub={sessionPnl !== null && initial > 0 ? fmtPct((sessionPnl / initial) * 100) : undefined}
        tone={sessionPnl === null ? undefined : pnlClass(sessionPnl)}
      />
      <Kpi
        label="Unrealized PnL"
        value={unrealized === null ? "-" : fmtSignedUsd(unrealized)}
        tone={unrealized === null ? undefined : pnlClass(unrealized)}
      />
      <Kpi
        label="Realized PnL"
        value={fmtSignedUsd(realized)}
        sub={`${closed.length} closes in view`}
        tone={pnlClass(realized)}
      />
      <Kpi label="Open positions" value={String(account?.positions.length ?? 0)} />
      <Kpi
        label="Win rate"
        value={closed.length === 0 ? "-" : fmtPlainPct((wins / closed.length) * 100)}
        sub={`${wins} / ${closed.length}`}
      />
    </div>
  );
}
