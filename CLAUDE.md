# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KavziTrader is an LLM-based cryptocurrency trading platform for Binance using a **Brain-Spine Architecture**. The Brain (tiered PydanticAI agents: Haiku → Sonnet → Opus) handles intelligent market analysis; the Spine handles deterministic, high-speed async execution. Python 3.13+, async-first, event-sourced via Redis Streams.

## Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/indicators/test_ema.py

# Run a single test
uv run pytest tests/indicators/test_ema.py::test_function_name -v

# Pre-commit checks (ruff lint + format, mypy, trailing whitespace, absolufy-imports)
uv run pre-commit run --all-files

# Individual quality checks
uv run ruff check .
uv run ruff format .
uv run mypy .

# CLI
uv run kavzitrader --help
uv run kavzitrader trade start --dry-run

# Redis (required runtime dependency)
cd docker && docker-compose up -d
```

## Architecture

### Brain-Spine Paradigm

**Brain (LLM Layer)** — `kavzi_trader/brain/`
- Tiered PydanticAI agents routed via OpenRouter: Scout (Haiku, ~500ms) → Analyst (Sonnet, ~2s) → Trader (Opus, ~5s)
- 90%+ filter rate at the cheap Scout tier before escalating
- `brain/config.py`: LLM configuration (model IDs, retries, API key)
- `brain/agent/factory.py`: Creates PydanticAI agents pointed at OpenRouter
- Jinja2-templated prompts in `brain/prompts/`, Pydantic output schemas in `brain/schemas/`
- Confidence calibration tracking in `brain/calibration/`
- Env var: `KT_OPENROUTER_API_KEY` for API access

**Spine (Execution Layer)** — `kavzi_trader/spine/`
- `execution/`: Order execution engine with staleness validation
- `risk/`: ATR-based dynamic risk validator, volatility calculator, position sizer
- `position/`: Active management — trailing stops, break-even, partial exits, scaling, time exits
- `state/`: Redis-backed state management (positions, orders, account balance)
- `filters/`: Pre-trade validation — liquidity, funding rate, correlation, news, movement

**Orchestrator** — `kavzi_trader/orchestrator/`
- Coordinates 5 concurrent async loops: DataIngest, OrderFlow, Reasoning, Execution, PositionManagement
- Latency separation: Brain operates at 500ms-5s; Spine responds in <100ms

**Other modules:**
- `api/binance/`: REST + WebSocket clients (spot, futures, user data streams)
- `indicators/`: Technical analysis (EMA, SMA, RSI, MACD, ATR, Bollinger Bands, OBV, Stochastic)
- `order_flow/`: Funding rate, open interest, liquidation level calculators
- `events/`: Redis Streams event sourcing (immutable audit trail)
- `paper/`: Binance Testnet paper trading mode
- `config/`: YAML + env-based configuration (`config/config.yaml`, `.env`)
- `cli/`: Click-based CLI (`trade`, `model`, `data`, `system`, `config` command groups)

### Key Data Flow

```
Candle Close → Scout (INTERESTING/SKIP) → Analyst (setup validation) → Trader (trade signal)
  → Pre-trade filters → Risk validation → Execution engine → Binance API
  → Event store (Redis Streams) → Position management loops
```

## Coding Conventions

- **Pydantic only** — no dataclasses. All models use `Schema` postfix (e.g., `TradeOrderSchema`). Use `Annotated[T, Field(...)]` syntax. Instantiate with `model_validate()`, never `**unpacking`. Use `ConfigDict(frozen=True)` for immutability.
- **One class per file** with related helpers allowed. snake_case filenames. DB models use `Model` postfix.
- **pathlib.Path only** — string paths are prohibited.
- **Time variables** must have `_ms` or `_s` suffix indicating units.
- **Logging**: Use `logger.exception()` in exception handlers (not `logger.error()`). Use `%`-style formatting in log messages, not f-strings. Include contextual `extra={}` for structured data.
- **All functions require complete type hints**. mypy strict mode with Pydantic plugin enforced.
- **Absolute imports only** (enforced by absolufy-imports hook).
- **Line length**: 88 chars. 4-space indentation. Ruff for lint + format.
- **No bare tuples** for structured data — use Pydantic models with named fields instead.
- **After every change**: Always run `uv run pre-commit run --all-files` and `uv run pytest` after making changes. Pre-commit covers ruff lint/format, mypy, trailing whitespace, and absolufy-imports — use it instead of running ruff/mypy individually. Do not consider a change complete until both pre-commit and tests pass.
