import { Badge } from "@/components/ui/badge";
import { Hint } from "@/components/ui/hint";
import { EmptyState, Panel, PanelHeader } from "@/components/ui/panel";
import { Table, Td, Th } from "@/components/ui/table";
import { fmtDuration, fmtPct, fmtPlainPct, fmtPrice } from "@/lib/format";
import { useSelectedSymbol } from "@/components/panels/SymbolTabs";
import { buildDecisionPath, type PathInput } from "@/lib/decisionPath";
import { bufferVerdict, sizeIfLong } from "@/lib/explain";
import type { TrendState, TrendSymbol } from "@/lib/protocol";
import { cn } from "@/lib/utils";
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

function PathHint({ input }: { input: PathInput }) {
  const path = buildDecisionPath(input);
  return (
    <div className="space-y-1.5">
      <dl className="grid grid-cols-[auto_auto_1fr] gap-x-2 gap-y-1">
        {path.steps.map((step) => (
          <div key={step.key} className="contents">
            <dt className="font-semibold text-muted-foreground">{step.label}</dt>
            <dd className="font-semibold tabular-nums">{step.value}</dd>
            <dd>{step.text}</dd>
          </div>
        ))}
      </dl>
      <p className="font-medium">{path.next}</p>
    </div>
  );
}

interface TrendRowProps {
  state: TrendState;
  symbol: TrendSymbol;
  price: number;
  selected: boolean;
  onSelect: () => void;
}

function TrendRow({ state, symbol, price, selected, onSelect }: TrendRowProps) {
  const position = useStore((s) => s.data.account?.positions.find((p) => p.symbol === symbol.symbol) ?? null);
  const decisions = useStore((s) => s.data.decisions);
  const trades = useStore((s) => s.data.trades);
  const nowMs = useNow();
  const isLong = symbol.signal > 0;
  const flip = flipDistance(symbol, price);
  const size = sizeIfLong(state, symbol);
  const n = state.lookback;
  const pct = (w: number) => fmtPlainPct(w * 100);
  return (
    <tr onClick={onSelect} className={cn("cursor-pointer hover:bg-muted/40", selected && "bg-sky-400/10")}>
      <Td className={cn("border-l-2 font-medium", selected ? "border-l-sky-400" : "border-l-transparent")}>
        {symbol.symbol}
      </Td>
      <Td>
        <Hint
          plain
          wide
          content={<PathHint input={{ state, symbol, price, position, decisions, trades, nowMs }} />}
        >
          <Badge tone={isLong ? "green" : "neutral"}>{isLong ? "LONG" : "FLAT"}</Badge>
        </Hint>
      </Td>
      <Td right>
        <Hint content={`Live price. The rule acted on the ${state.day} daily close of ${fmtPrice(symbol.close)}.`}>
          {fmtPrice(price)}
        </Hint>
      </Td>
      <Td>
        <div className="flex items-center gap-2 text-xs">
          <Hint className="text-loss" content={`Lowest of the last ${n} daily closes. A close below it turns the symbol FLAT.`}>
            {fmtPrice(symbol.exit_level)}
          </Hint>
          <Hint plain content={`Where the live price sits in the ${n}-day channel: left edge is the exit level, right edge is the entry level.`}>
            <ChannelBar low={symbol.exit_level} high={symbol.entry_level} price={price} />
          </Hint>
          <Hint className="text-profit" content={`Highest of the last ${n} daily closes. A close above it turns the symbol LONG.`}>
            {fmtPrice(symbol.entry_level)}
          </Hint>
        </div>
      </Td>
      <Td right className={flip.target === "entry" ? "text-profit" : "text-loss"}>
        <Hint
          content={`The price must move ${fmtPct(flip.pct)} and close the UTC day there to turn ${flip.target === "entry" ? "LONG" : "FLAT"}.`}
        >
          {fmtPct(flip.pct)} <span className="text-xs text-muted-foreground">to {flip.target}</span>
        </Hint>
      </Td>
      <Td right>
        {symbol.annual_vol === null ? (
          <Hint content={`Needs ${state.vol_window} daily returns before sizing can start.`}>-</Hint>
        ) : (
          <Hint
            content={`Annualised ${state.vol_window}-day vol. Size if long: min(${pct(state.annual_vol_target)} ÷ ${pct(symbol.annual_vol)}, ${state.max_leverage}×) ÷ ${state.symbols.length} = ${size === null ? "-" : pct(size)}.`}
          >
            {pct(symbol.annual_vol)}
          </Hint>
        )}
      </Td>
      <Td right>
        <Hint content={`Signal ${symbol.signal} × size. What the rule wants to hold before the buffer.`}>
          {pct(symbol.target_weight)}
        </Hint>
      </Td>
      <Td right>
        <Hint content={bufferVerdict(symbol.target_weight, symbol.held_weight, state.buffer_band).text}>
          {pct(symbol.held_weight)}
        </Hint>
      </Td>
    </tr>
  );
}

export function TrendPanel() {
  const trend = useStore((s) => s.data.trend);
  const selected = useSelectedSymbol();
  const selectSymbol = useStore((s) => s.selectSymbol);
  const prices = useStore((s) => s.data.account?.prices);
  const now = useNow();
  return (
    <Panel>
      <PanelHeader title="Trend model">
        {trend && (
          <span className="text-xs text-muted-foreground">
            <Hint
              content={`Long when a daily close breaks above the previous ${trend.lookback}-day high, flat when one breaks below the ${trend.lookback}-day low. It never shorts: the long/short variant backtested worse (Sharpe 0.27 vs 0.45, drawdown -29% vs -19%, 2022-2026). Click a row for the full decision path.`}
            >
              {trend.lookback}d Donchian, long/flat (no shorts)
            </Hint>{" "}
            · state of {trend.day} close · next rebalance in{" "}
            <Hint
              className="tabular-nums text-foreground"
              content="The rule runs once a day at 00:01 UTC, a minute after Binance closes the daily bar. Nothing trades between runs except the disaster stop."
            >
              {fmtDuration(trend.next_rebalance_ms - now)}
            </Hint>
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
              <Th hint="LONG holds the coin at its target weight; FLAT holds nothing. There is no SHORT state. Hover a badge for why.">State</Th>
              <Th right hint="Latest price from the exchange">Live</Th>
              <Th hint={`Exit level (${trend.lookback}-day low), live price, entry level (${trend.lookback}-day high)`}>
                Channel
              </Th>
              <Th right hint="Move from the live price to the level a daily close must break; only the 00:00 UTC close counts">
                Flip
              </Th>
              <Th right hint={`Annualised realised volatility over ${trend.vol_window} days; it sets the position size`}>
                Vol
              </Th>
              <Th right hint="Weight of equity the rule wants, before the turnover buffer">Target</Th>
              <Th right hint={`Weight actually held after the ${fmtPlainPct(trend.buffer_band * 100)} turnover buffer`}>
                Held
              </Th>
            </tr>
          </thead>
          <tbody>
            {trend.symbols.map((s) => {
              const live = Number(prices?.[s.symbol]);
              return (
                <TrendRow
                  key={s.symbol}
                  state={trend}
                  symbol={s}
                  price={Number.isFinite(live) && live > 0 ? live : s.close}
                  selected={s.symbol === selected}
                  onSelect={() => selectSymbol(s.symbol)}
                />
              );
            })}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}
