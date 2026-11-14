import { BottomPanel } from "@/components/panels/BottomPanel";
import { ChartPanel } from "@/components/panels/ChartPanel";
import { DecisionFeed } from "@/components/panels/DecisionFeed";
import { KpiRow } from "@/components/panels/KpiRow";
import { PositionsTable } from "@/components/panels/PositionsTable";
import { TopBar } from "@/components/panels/TopBar";

export function App() {
  return (
    <div className="min-h-screen">
      <TopBar />
      <main className="mx-auto flex max-w-[2560px] flex-col gap-3 p-3">
        <KpiRow />
        <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="flex min-w-0 flex-col gap-3">
            <ChartPanel />
            <PositionsTable />
          </div>
          <div className="relative min-h-[480px]">
            <div className="inset-0 h-[480px] lg:absolute lg:h-auto">
              <DecisionFeed />
            </div>
          </div>
        </div>
        <BottomPanel />
      </main>
    </div>
  );
}
