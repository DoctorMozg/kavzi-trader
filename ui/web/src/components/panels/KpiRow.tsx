import { Hint } from "@/components/ui/hint";
import { fmtPct, fmtPlainPct, fmtSignedUsd, fmtUsd, pnlClass } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useStore } from "@/state/store";

interface KpiProps {
  label: string;
  hint: string;
  value: string;
  sub?: string;
  tone?: string;
}

function Kpi({ label, hint, value, sub, tone }: KpiProps) {
  return (
    <div className="min-w-0 rounded-lg border bg-card px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        <Hint content={hint}>{label}</Hint>
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
      <Kpi label="Balance" hint="Wallet balance in USDT, realised PnL included, open positions excluded." value={balance === null ? "-" : fmtUsd(balance)} sub="USDT" />
      <Kpi
        label="Session PnL"
        hint="Balance change since the starting balance of this paper account, realised only."
        value={sessionPnl === null ? "-" : fmtSignedUsd(sessionPnl)}
        sub={sessionPnl !== null && initial > 0 ? fmtPct((sessionPnl / initial) * 100) : undefined}
        tone={sessionPnl === null ? undefined : pnlClass(sessionPnl)}
      />
      <Kpi
        label="Unrealized PnL"
        hint="Mark-to-market profit or loss of open positions at the live price."
        value={unrealized === null ? "-" : fmtSignedUsd(unrealized)}
        tone={unrealized === null ? undefined : pnlClass(unrealized)}
      />
      <Kpi
        label="Realized PnL"
        hint="Sum of PnL over the closed positions shown in this dashboard session."
        value={fmtSignedUsd(realized)}
        sub={`${closed.length} closes in view`}
        tone={pnlClass(realized)}
      />
      <Kpi label="Open positions" hint="Positions currently held. The trend rule holds at most one per symbol, LONG only." value={String(account?.positions.length ?? 0)} />
      <Kpi
        label="Win rate"
        hint="Share of closed positions with positive PnL. Trend following usually wins under half its trades and earns from a few large winners."
        value={closed.length === 0 ? "-" : fmtPlainPct((wins / closed.length) * 100)}
        sub={`${wins} / ${closed.length}`}
      />
    </div>
  );
}
