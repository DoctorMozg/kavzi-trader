import type {
  Account,
  Candle,
  CandlesEvent,
  ClosedPosition,
  Decision,
  ServerMessage,
  UiEventPayload,
  Trade,
  GateInputs,
  TrendState,
} from "@/lib/protocol";

export const CAPS = { decisions: 300, trades: 200, closed: 200, candles: 500 } as const;

export interface DashboardState {
  seq: number | null;
  account: Account | null;
  decisions: Decision[];
  trades: Trade[];
  closed: ClosedPosition[];
  candles: Record<string, Candle[]>;
  candleInterval: string | null;
  trend: TrendState | null;
  gateInputs: GateInputs | null;
}

export const initialState: DashboardState = {
  seq: null,
  account: null,
  decisions: [],
  trades: [],
  closed: [],
  candles: {},
  candleInterval: null,
  trend: null,
  gateInputs: null,
};

function capTail<T>(items: T[], cap: number): T[] {
  return items.length > cap ? items.slice(items.length - cap) : items;
}

function append<T>(items: T[], item: T, cap: number): T[] {
  return capTail([...items, item], cap);
}

export function mergeCandles(existing: Candle[], incoming: Candle[]): Candle[] {
  const byOpenTime = new Map<number, Candle>();
  for (const candle of existing) byOpenTime.set(candle.open_time_ms, candle);
  for (const candle of incoming) byOpenTime.set(candle.open_time_ms, candle);
  const sorted = [...byOpenTime.values()].sort((a, b) => a.open_time_ms - b.open_time_ms);
  return capTail(sorted, CAPS.candles);
}

function applyCandles(state: DashboardState, event: CandlesEvent): DashboardState {
  const merged = mergeCandles(state.candles[event.symbol] ?? [], event.candles);
  return {
    ...state,
    candles: { ...state.candles, [event.symbol]: merged },
    candleInterval: event.interval,
  };
}

function applyEvent(state: DashboardState, event: UiEventPayload): DashboardState {
  switch (event.type) {
    case "account":
      return { ...state, account: event };
    case "decision":
      return { ...state, decisions: append(state.decisions, event, CAPS.decisions) };
    case "trade":
      return { ...state, trades: append(state.trades, event, CAPS.trades) };
    case "position_closed":
      return { ...state, closed: append(state.closed, event, CAPS.closed) };
    case "candles":
      return applyCandles(state, event);
    case "trend_state":
      return { ...state, trend: event };
    case "gate_inputs":
      return { ...state, gateInputs: event };
  }
}

export function applyMessage(state: DashboardState, msg: ServerMessage): DashboardState {
  if (msg.type === "snapshot") {
    const { snapshot } = msg;
    return {
      seq: msg.seq,
      account: snapshot.account,
      decisions: capTail(snapshot.decisions, CAPS.decisions),
      trades: capTail(snapshot.trades, CAPS.trades),
      closed: capTail(snapshot.closed_positions, CAPS.closed),
      candles: Object.fromEntries(
        Object.entries(snapshot.candles).map(([symbol, list]) => [
          symbol,
          mergeCandles([], list),
        ]),
      ),
      candleInterval: snapshot.candle_interval,
      trend: snapshot.trend,
      gateInputs: snapshot.gate_inputs,
    };
  }
  return { ...applyEvent(state, msg.event), seq: msg.seq };
}
