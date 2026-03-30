---
name: analyze-run
description: Analyze the latest KavziTrader trading run logs using the run-analyzer agent
user_invocable: true
---

# Analyze Run

Launch the `run-analyzer` agent to analyze the latest trading session logs.

## Steps

1. Use the `Agent` tool with `subagent_type: "run-analyzer"` to launch the analysis
2. The prompt should instruct the agent to follow its built-in analysis framework against the latest log file
3. After the agent completes, summarize the key findings to the user and point them to the generated report file

## Prompt

```
Analyze the latest KavziTrader trading run. Follow your full analysis framework: extract the decision timeline, evaluate Scout/Analyst/Trader performance, validate against market data, calculate metrics, and save the report.
```
