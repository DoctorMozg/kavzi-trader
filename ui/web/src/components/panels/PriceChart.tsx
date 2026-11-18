import {
  CandlestickSeries,
  createChart,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import { EmptyState } from "@/components/ui/panel";
import { CHART_COLORS, chartOptions, toChartTime } from "@/lib/chartTheme";
import { nextLiveBar, type LiveExtremes } from "@/lib/liveBar";
import type { Candle } from "@/lib/protocol";
import { useStore } from "@/state/store";

const EMPTY: Candle[] = [];

const toBar = (c: Candle) => ({
  time: toChartTime(c.open_time_ms),
  open: Number(c.open),
  high: Number(c.high),
  low: Number(c.low),
  close: Number(c.close),
});

interface Level {
  price: number;
  title: string;
  color: string;
}

function useLevels(symbol: string): Level[] {
  const positions = useStore((s) => s.data.account?.positions);
  // Positions arrive ~1Hz as fresh objects; key on the levels so lines only redraw on change.
  const key = (positions ?? [])
    .filter((p) => p.symbol === symbol)
    .map((p) => `${p.side}|${p.entry_price}|${p.stop_loss}|${p.take_profit}`)
    .join(";");
  return useMemo(
    () =>
      key === ""
        ? []
        : key.split(";").flatMap((entry) => {
            const [side, e, sl, tp] = entry.split("|") as [string, string, string, string];
            return [
              { price: Number(e), title: `${side} entry`, color: CHART_COLORS.accent },
              { price: Number(sl), title: "SL", color: CHART_COLORS.down },
              // Trend positions exit on signal and carry no take-profit.
              ...(tp === "null" ? [] : [{ price: Number(tp), title: "TP", color: CHART_COLORS.up }]),
            ];
          }),
    [key],
  );
}

export function PriceChart({ symbol }: { symbol: string }) {
  const candles = useStore((s) => s.data.candles[symbol]) ?? EMPTY;
  const priceText = useStore((s) => s.data.account?.prices[symbol]);
  const levels = useLevels(symbol);

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const linesRef = useRef<IPriceLine[]>([]);
  const extremesRef = useRef<LiveExtremes | null>(null);
  const fittedRef = useRef<string | null>(null);

  useEffect(() => {
    const chart = createChart(containerRef.current!, chartOptions);
    chartRef.current = chart;
    seriesRef.current = chart.addSeries(CandlestickSeries, {
      upColor: CHART_COLORS.up,
      downColor: CHART_COLORS.down,
      wickUpColor: CHART_COLORS.up,
      wickDownColor: CHART_COLORS.down,
      borderVisible: false,
    });
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      linesRef.current = [];
      fittedRef.current = null;
    };
  }, []);

  useEffect(() => {
    seriesRef.current?.setData(candles.map(toBar));
    extremesRef.current = null;
    if (candles.length > 0 && fittedRef.current !== symbol) {
      chartRef.current?.timeScale().fitContent();
      fittedRef.current = symbol;
    }
  }, [candles, symbol]);

  useEffect(() => {
    const last = candles.at(-1);
    const price = Number(priceText);
    if (!last || !priceText || !Number.isFinite(price)) return;
    const { bar, extremes } = nextLiveBar(last, price, extremesRef.current);
    extremesRef.current = extremes;
    seriesRef.current?.update({ ...bar, time: toChartTime(bar.openTimeMs) });
  }, [candles, priceText]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    for (const line of linesRef.current) series.removePriceLine(line);
    linesRef.current = levels.map((level) =>
      series.createPriceLine({
        price: level.price,
        title: level.title,
        color: level.color,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
      }),
    );
  }, [levels, symbol]);

  return (
    <div className="relative h-full min-h-0">
      <div ref={containerRef} className="absolute inset-0" />
      {candles.length === 0 && (
        <div className="absolute inset-0">
          <EmptyState>No candles for {symbol} yet</EmptyState>
        </div>
      )}
    </div>
  );
}
