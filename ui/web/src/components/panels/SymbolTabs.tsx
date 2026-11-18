import { useShallow } from "zustand/react/shallow";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useStore } from "@/state/store";

export function useSymbols(): string[] {
  return useStore(
    useShallow((s) => {
      const keys = new Set([
        ...Object.keys(s.data.candles),
        ...Object.keys(s.data.account?.prices ?? {}),
      ]);
      return [...keys].sort();
    }),
  );
}

export function useSelectedSymbol(): string {
  const symbols = useSymbols();
  const selected = useStore((s) => s.selectedSymbol);
  return symbols.includes(selected) ? selected : (symbols[0] ?? "");
}

export function SymbolTabs({
  symbols,
  value,
  onChange,
}: {
  symbols: string[];
  value: string;
  onChange: (symbol: string) => void;
}) {
  return (
    <Tabs value={value} onValueChange={onChange}>
      <TabsList>
        {symbols.map((symbol) => (
          <TabsTrigger key={symbol} value={symbol}>
            {symbol}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
