# LLM news gate on trend entries, rules fixed 2026-11-17

The LLM pipeline lost to buy-and-hold in its July 2026 replay, and the
research note finds no published net edge for LLMs choosing direction
(`.mz/research/2026_11_17_research_trading_bot_sota.md`). The one input with
some post-cutoff evidence is news. So the LLM gets a narrow job: read recent
headlines when the lookback-20 trend rule opens a long, and VETO only on a
concrete negative catalyst the price rule cannot see. This file fixes how the
gate is scored before any gate call is made.

## Gate

- Prompt: `brain/prompts/templates/system/agents/trend_gate.j2` and
  `user/requests/review_trend_entry.j2` as of commit 942bf6c. Every review
  logs the first 12 hex digits of the system prompt's SHA-256; a different
  hash is a different trial.
- Model `claude-sonnet-5-5`, effort medium, 3 samples per entry, VETO only on
  a majority (2 of 3). An entry with no headlines in the window is KEEP
  without a call.
- Headlines: `NewsStore` under `data/news`, published in the 72 h before the
  review time and at least 2 h before it (date-only items 30 h more), coin
  mentions first, 30 at most.
- Review time: one minute after the daily close that triggered the entry,
  when the live plugin would run.
- The gate is shadow only. It logs and never changes a trade.

## Part A: one replay over July-October 2026 (run once)

    uv run kavzitrader eval gate-replay --from 2026-07-01 --to 2026-10-31

- Entries: flat-to-long trades of `TrendEntryFinder` with lookbacks {20},
  the 20% buffer warmed up from 2022-03-14, commission 0.0005 and daily
  funding, signal days 2026-07-01 to 2026-10-31. That is 15 entries. All of
  them come after the June 2026 training cutoff.
- Outcome per entry: `net_pnl`, the symbol's weighted net return from entry
  to exit (costs and funding included), or to 2026-10-31 if still open.
- Veto value = minus the sum of `net_pnl` over vetoed entries. Above zero
  means the vetoes removed money-losing trades.
- Headlines: the July-October backfill (Cointelegraph with exact times, The
  Block at day precision). Backfilled titles are the pages as they read in
  November 2026, so later edits can leak. This is a known weakness of Part A.

Decision for Part A:

- KILL the gate if it vetoes more than 5 of the 15 entries (it would be
  overriding the rule, not catching rare events), or if veto value < 0.
- Otherwise keep running Part B. With no vetoes the replay says nothing
  either way.
- Part A cannot adopt the gate. With 15 entries even a perfect result is
  anecdote.

Disclosure: the entry list and each entry's `net_pnl` were printed while
building the replay, before this file was written and before any gate call.
The prompt was committed before that (942bf6c). The thresholds above do not
depend on which entries won.

## Part B: live shadow log (scored on or after 2027-11-17)

- Source: `results/trend_gate/shadow.jsonl`, written by the paper trend
  plugin with `strategy.trend_following.gate.enabled: true`, only reviews
  with the prompt hash above.
- Outcome per entry: `net_pnl` computed as in Part A from the archive once it
  covers the exit.
- ADOPT as a real (blocking) gate only if all of these hold: at least 40
  reviewed entries; veto value > 0; vetoed entries' mean `net_pnl` below kept
  entries' mean; and no more than a third of entries vetoed. An adopted gate
  then goes through its own paper forward test.
- Otherwise drop the gate. No threshold, prompt or model in this file may
  change after the first gate call; a change starts a new trial.
