import { ClosedTable } from "@/components/panels/ClosedTable";
import { EquityChart } from "@/components/panels/EquityChart";
import { SystemPanel } from "@/components/panels/SystemPanel";
import { TradesTable } from "@/components/panels/TradesTable";
import { Panel } from "@/components/ui/panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function BottomPanel() {
  return (
    <Panel>
      <Tabs defaultValue="trades" className="flex min-h-0 flex-col">
        <div className="border-b px-3 py-1.5">
          <TabsList>
            <TabsTrigger value="trades">Trades</TabsTrigger>
            <TabsTrigger value="closed">Closed positions</TabsTrigger>
            <TabsTrigger value="equity">Equity</TabsTrigger>
            <TabsTrigger value="system">System</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="trades" className="max-h-80 overflow-auto">
          <TradesTable />
        </TabsContent>
        <TabsContent value="closed" className="max-h-80 overflow-auto">
          <ClosedTable />
        </TabsContent>
        <TabsContent value="equity">
          <EquityChart />
        </TabsContent>
        <TabsContent value="system">
          <SystemPanel />
        </TabsContent>
      </Tabs>
    </Panel>
  );
}
