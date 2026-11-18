import { useSelectedSymbol } from "@/components/panels/SymbolTabs";
import { Badge } from "@/components/ui/badge";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { fmtDuration } from "@/lib/format";
import { useNow } from "@/lib/useNow";
import { useStore } from "@/state/store";

// Fixed by evals/preregistrations/2026_11_17_trend_news_gate.md (Part B).
const MIN_ENTRIES = 40;
const SCORE_DATE = "2027-11-17";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[6.5rem_1fr] gap-x-2 text-xs leading-snug">
      <span className="font-medium text-muted-foreground">{label}</span>
      <div>{children}</div>
    </div>
  );
}

export function ShadowGatePanel() {
  const gate = useStore((s) => s.data.gateInputs);
  const decisions = useStore((s) => s.data.decisions);
  const symbol = useSelectedSymbol();
  const nowMs = useNow();
  const coin = symbol.replace(/USDT$/, "");
  const lastReview = decisions.findLast((d) => d.stage === "gate" && d.symbol === symbol);
  const reviews = gate?.reviews ?? 0;
  return (
    <Panel>
      <PanelHeader title="Shadow experiment: LLM news gate">
        <Badge tone="violet">no effect on trades</Badge>
      </PanelHeader>
      <div className="space-y-2 p-3">
        <Row label="Question">
          Would an LLM reading the news have skipped trend entries that went on to lose money?
        </Row>
        <Row label="How">
          When step 4 opens a new LONG, {gate?.model_id ?? "the gate model"} reads up to 30 headlines from
          the last {gate?.window_h ?? 72} h, {gate?.samples ?? 3} times, and votes KEEP or VETO; the majority
          wins. The vote is only logged. The order goes through either way, so we can later compare vetoed and
          kept entries on real outcomes.
        </Row>
        <Row label="Input now">
          {gate ? (
            <>
              {gate.headlines} headlines in the window, {gate.coin_headlines[coin] ?? 0} tagged {coin}
              {gate.newest_ms !== null && <>, newest {fmtDuration(nowMs - gate.newest_ms)} ago</>}. The others count
              as market-wide news.
            </>
          ) : (
            "No report yet"
          )}
        </Row>
        <Row label={`Last on ${coin || "symbol"}`}>
          {lastReview ? (
            <>
              <span className="font-semibold">{lastReview.verdict}</span> {fmtDuration(nowMs - lastReview.ts_ms)} ago:{" "}
              {lastReview.summary}
            </>
          ) : (
            "No review yet; it runs only when this coin turns LONG."
          )}
        </Row>
        <Row label="Progress">
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-28 overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-violet-400" style={{ width: `${Math.min(reviews / MIN_ENTRIES, 1) * 100}%` }} />
            </div>
            <span className="tabular-nums">
              {reviews} / {MIN_ENTRIES} live entries, {gate?.vetoes ?? 0} vetoed
            </span>
          </div>
          <div className="mt-0.5 text-muted-foreground">
            Scored once, on or after {SCORE_DATE}. The Jul to Oct 2026 replay had 15 entries and 0 vetoes (45 of 45
            votes KEEP), so there is no evidence either way yet.
          </div>
        </Row>
        <Row label="Pays off if">
          It becomes a real filter only if, over 40+ entries, vetoed entries did worse than kept ones, the vetoes
          saved money in total, and no more than a third were vetoed. Otherwise it is dropped.
        </Row>
        <Row label="Not used">
          Fear &amp; Greed and DVOL feed only the LLM pipeline strategy; the trend rule never fetches them.
        </Row>
      </div>
    </Panel>
  );
}
