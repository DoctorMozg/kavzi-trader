# Prompt Reference

This document lists the prompt templates used by the tiered LLM agents and how
they are rendered.

## Template Engine

The prompt loader lives at `kavzi_trader/brain/prompts/loader.py` and renders
templates from `kavzi_trader/brain/prompts/templates/` using Jinja2.

## System Prompts

System prompts define behavior and never change per request.

```
brain/prompts/templates/system/
├── base/role.j2
├── base/risk_rules.j2
├── base/output_format.j2
└── agents/
    ├── scout.j2
    ├── analyst.j2
    └── trader.j2
```

## User Prompts

User prompts carry the current market context and vary every request.

```
brain/prompts/templates/user/
├── context/
│   ├── market_snapshot.j2
│   ├── order_flow.j2
│   ├── algorithm_confluence.j2
│   └── account_state.j2
└── requests/
    ├── scout_scan.j2
    ├── analyze_setup.j2
    └── make_decision.j2
```

## Rendering Flow

The agent code renders a system prompt once per agent and a user prompt on each
call.

```
system_prompt = loader.render_system_prompt("scout")
user_prompt = loader.render_user_prompt("scout_scan", context)
```

Context values are JSON strings produced by the `ContextBuilder` in
`kavzi_trader/brain/context/builder.py`.
