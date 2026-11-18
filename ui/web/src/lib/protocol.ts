import type {
  UiAccountEventSchema,
  UiCandleSchema,
  UiCandlesEventSchema,
  UiDecisionEventSchema,
  UiEvent,
  UiEventMessageSchema,
  UiGateInputsEventSchema,
  UiOpenPositionSchema,
  UiPositionClosedEventSchema,
  UiServerMessage,
  UiSnapshotMessageSchema,
  UiSnapshotSchema,
  UiTradeEventSchema,
  UiTrendDaySchema,
  UiTrendStateEventSchema,
  UiTrendSymbolSchema,
} from "@/generated/ui-types";

export type ServerMessage = UiServerMessage;
export type SnapshotMessage = UiSnapshotMessageSchema;
export type EventMessage = UiEventMessageSchema;
export type Snapshot = UiSnapshotSchema;
export type UiEventPayload = UiEvent;
export type Account = UiAccountEventSchema;
export type OpenPosition = UiOpenPositionSchema;
export type Decision = UiDecisionEventSchema;
export type Trade = UiTradeEventSchema;
export type ClosedPosition = UiPositionClosedEventSchema;
export type CandlesEvent = UiCandlesEventSchema;
export type Candle = UiCandleSchema;
export type Stage = Decision["stage"];
export type TrendState = UiTrendStateEventSchema;
export type TrendSymbol = UiTrendSymbolSchema;
export type TrendDay = UiTrendDaySchema;
export type GateInputs = UiGateInputsEventSchema;
