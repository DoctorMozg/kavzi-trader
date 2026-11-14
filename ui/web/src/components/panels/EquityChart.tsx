import {
  AreaSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import { EmptyState } from "@/components/ui/panel";
import { CHART_COLORS, chartOptions, toChartTime } from "@/lib/chartTheme";
import { equityCurve } from "@/lib/equity";
import { useStore } from "@/state/store";

export function EquityChart() {
  const closed = useStore((s) => s.data.closed);
  const startMs = useStore((s) => s.data.account?.session_started_at_ms ?? null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    const chart = createChart(containerRef.current!, chartOptions);
    chartRef.current = chart;
    // The tab mounts this chart at zero width, so refit once real size arrives.
    const observer = new ResizeObserver(() => chart.timeScale().fitContent());
    observer.observe(containerRef.current!);
    seriesRef.current = chart.addSeries(AreaSeries, {
      lineColor: CHART_COLORS.accent,
      topColor: "rgba(91, 141, 239, 0.3)",
      bottomColor: "rgba(91, 141, 239, 0)",
      lineWidth: 2,
    });
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const points = equityCurve(closed, startMs);
    seriesRef.current?.setData(
      points.map((p) => ({ time: toChartTime(p.timeS * 1000), value: p.value })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [closed, startMs]);

  return (
    <div className="relative h-72">
      <div ref={containerRef} className="absolute inset-0" />
      {closed.length === 0 && (
        <div className="absolute inset-0">
          <EmptyState>No realized PnL yet</EmptyState>
        </div>
      )}
    </div>
  );
}
