import { Badge } from "@/components/ui/badge";

export function SideBadge({ side }: { side: "LONG" | "SHORT" | "CLOSE" }) {
  return <Badge tone={side === "LONG" ? "green" : side === "SHORT" ? "red" : "neutral"}>{side}</Badge>;
}
