import {
  createChart,
  createSeriesMarkers,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import { EmptyState } from "@/components/ui/panel";
import { CHART_COLORS, chartOptions, toChartTime } from "@/lib/chartTheme";
import type { TrendSymbol } from "@/lib/protocol";
import { DAY_MS, tradeMarks } from "@/lib/trend";
import { useStore } from "@/state/store";

const FLAT_COLOR = CHART_COLORS.text;

interface DailySeries {
  close: LineData<Time>[];
  upper: LineData<Time>[];
  lower: LineData<Time>[];
  todayMs: number;
}

// Closed days, plus today's forming point at the levels the next close must break.
function dailySeries(symbol: TrendSymbol): DailySeries {
  const close: LineData<Time>[] = [];
  const upper: LineData<Time>[] = [];
  const lower: LineData<Time>[] = [];
  for (const day of symbol.days) {
    const time = toChartTime(day.day_ms);
    close.push({ time, value: day.close, color: day.signal > 0 ? CHART_COLORS.up : FLAT_COLOR });
    if (day.upper !== null) upper.push({ time, value: day.upper });
    if (day.lower !== null) lower.push({ time, value: day.lower });
  }
  const todayMs = (symbol.days.at(-1)?.day_ms ?? 0) + DAY_MS;
  upper.push({ time: toChartTime(todayMs), value: symbol.entry_level });
  lower.push({ time: toChartTime(todayMs), value: symbol.exit_level });
  return { close, upper, lower, todayMs };
}

function channelLine(chart: IChartApi, color: string, title: string): ISeriesApi<"Line"> {
  return chart.addSeries(LineSeries, {
    color,
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    title,
    priceLineVisible: false,
    crosshairMarkerVisible: false,
  });
}

export function DailyChart({ symbol }: { symbol: string }) {
  const trendSymbol = useStore((s) => s.data.trend?.symbols.find((t) => t.symbol === symbol));
  const lookback = useStore((s) => s.data.trend?.lookback);
  const priceText = useStore((s) => s.data.account?.prices[symbol]);
  const trades = useStore((s) => s.data.trades);
  const closed = useStore((s) => s.data.closed);
  const series = useMemo(() => (trendSymbol ? dailySeries(trendSymbol) : null), [trendSymbol]);
  const marks = useMemo(() => tradeMarks(symbol, trades, closed), [symbol, trades, closed]);

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const closeRef = useRef<ISeriesApi<"Line"> | null>(null);
  const upperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const lowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const fittedRef = useRef<string | null>(null);

  useEffect(() => {
    const chart = createChart(containerRef.current!, {
      ...chartOptions,
      timeScale: { ...chartOptions.timeScale, timeVisible: false },
    });
    chartRef.current = chart;
    closeRef.current = chart.addSeries(LineSeries, { lineWidth: 2, priceLineVisible: false });
    upperRef.current = channelLine(chart, CHART_COLORS.up, "entry");
    lowerRef.current = channelLine(chart, CHART_COLORS.down, "exit");
    markersRef.current = createSeriesMarkers(closeRef.current, []);
    return () => {
      chart.remove();
      chartRef.current = null;
      closeRef.current = null;
      upperRef.current = null;
      lowerRef.current = null;
      markersRef.current = null;
      fittedRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!series) return;
    closeRef.current?.setData(series.close);
    upperRef.current?.setData(series.upper);
    lowerRef.current?.setData(series.lower);
    if (fittedRef.current !== symbol) {
      chartRef.current?.timeScale().fitContent();
      fittedRef.current = symbol;
    }
  }, [series, symbol]);

  useEffect(() => {
    const price = Number(priceText);
    if (!series || !priceText || !Number.isFinite(price)) return;
    closeRef.current?.update({ time: toChartTime(series.todayMs), value: price, color: CHART_COLORS.accent });
  }, [series, priceText]);

  useEffect(() => {
    const markers: SeriesMarker<Time>[] = marks.map((m) =>
      m.kind === "entry"
        ? { time: toChartTime(m.dayMs), position: "belowBar", shape: "arrowUp", color: CHART_COLORS.up, text: m.text }
        : { time: toChartTime(m.dayMs), position: "aboveBar", shape: "arrowDown", color: CHART_COLORS.down, text: m.text },
    );
    markersRef.current?.setMarkers(markers);
  }, [marks, series]);

  return (
    <div className="relative h-full min-h-0">
      <div ref={containerRef} className="absolute inset-0" />
      {series ? (
        <div className="pointer-events-none absolute left-2 top-1 z-10 flex gap-3 text-[11px] text-muted-foreground">
          <span>
            <span className="text-profit">- -</span> {lookback}d high: entry
          </span>
          <span>
            <span className="text-loss">- -</span> {lookback}d low: exit
          </span>
          <span>
            <span className="text-profit">━</span> long <span className="ml-1">━</span> flat
          </span>
        </div>
      ) : (
        <div className="absolute inset-0">
          <EmptyState>No trend state for {symbol} yet</EmptyState>
        </div>
      )}
    </div>
  );
}
