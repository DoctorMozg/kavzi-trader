# KavziTrader TODO

## Scope

This document captures near-term, actionable tasks that are not yet scheduled
in the implementation plan.

## News Sourcing

Goal: Provide reliable, low-latency macro and crypto market events for the
news filter and LLM context.

### Data Sources (Priority Order)

1. **Economic Calendar (Macro)**
   - Focus: FOMC, CPI, NFP, GDP, ECB/BOE rate decisions
   - Requirements: UTC timestamps, event impact level, country

2. **Crypto-Specific News**
   - Focus: Major exchange outages, ETF approvals/denials, protocol exploits,
     chain halts, major upgrade schedules
   - Requirements: event timestamp, source credibility, category

3. **On-Chain / Exchange Status**
   - Focus: network congestion, withdrawal halts, maintenance windows
   - Requirements: start/end windows, affected assets

### Integration Tasks

- Create `NewsEventSchema` ingest adapter for the chosen calendar provider
- Normalize event times to UTC and emit `start_time`/`end_time`
- Add event severity to allow selective blocking (e.g., only HIGH impact)
- Cache events daily and refresh on schedule (e.g., every 15 minutes)
- Add fallback provider to avoid single-source outages

### Acceptance Criteria

- News filter blocks trades in the defined window for HIGH impact events
- Events are available for the next 7 days at minimum
- Failure to fetch events does not block trading (fail-open)

## LLM Integration Follow-ups

- Measure Scout filter rate over live data
- Validate TradeDecisionSchema outputs against real prompts
- Track confidence calibration accuracy after 50+ decisions

## Recently Completed

- Execution engine and orchestrator scaffolding
- Redis Streams event store with projections
- Testnet trading mode and CLI commands
