import {
  ColorType,
  type ChartOptions,
  type DeepPartial,
  type UTCTimestamp,
} from "lightweight-charts";

export const CHART_COLORS = {
  up: "#3fcf8e",
  down: "#f0616d",
  text: "#9aa0ad",
  grid: "#1f2330",
  accent: "#5b8def",
  warn: "#e6b450",
} as const;

export const chartOptions: DeepPartial<ChartOptions> = {
  autoSize: true,
  layout: {
    background: { type: ColorType.Solid, color: "transparent" },
    textColor: CHART_COLORS.text,
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
    attributionLogo: true,
  },
  grid: {
    vertLines: { color: CHART_COLORS.grid },
    horzLines: { color: CHART_COLORS.grid },
  },
  rightPriceScale: { borderColor: CHART_COLORS.grid },
  timeScale: { borderColor: CHART_COLORS.grid, timeVisible: true, secondsVisible: false },
};

// lightweight-charts renders axis labels in UTC; shifting by the local offset makes
// them match the local times shown in the tables.
export function toChartTime(ms: number): UTCTimestamp {
  const offsetS = new Date(ms).getTimezoneOffset() * 60;
  return (Math.floor(ms / 1000) - offsetS) as UTCTimestamp;
}
