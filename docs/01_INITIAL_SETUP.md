# KavziTrader: LLM-Based Crypto Trading Platform

## Project Overview

KavziTrader is an automated trading platform designed to leverage Large Language Models (LLMs) for crypto trading on Binance. The platform implements a **Brain-Spine Architecture** that decouples cognitive reasoning (LLM) from deterministic execution, enabling sophisticated AI-driven trading while maintaining real-time market responsiveness.

## Documentation

| Document | Description |
|----------|-------------|
| [01_INITIAL_SETUP.md](01_INITIAL_SETUP.md) | This document - project overview and setup |
| [02_ARCHITECTURE.md](02_ARCHITECTURE.md) | System architecture and Brain-Spine paradigm |
| [03_LLM_ARCHITECTURE.md](03_LLM_ARCHITECTURE.md) | LLM integration with tiered agents + Jinja2 prompts |
| [04_CODING_STANDARDS.md](04_CODING_STANDARDS.md) | Coding standards and best practices |
| [05_IMPLEMENTATION_PLAN.md](05_IMPLEMENTATION_PLAN.md) | Phased implementation roadmap |
| [06_SPINE_IMPLEMENTATION.md](06_SPINE_IMPLEMENTATION.md) | Execution layer, dynamic risk, position management |
| [07_TRADING_PLAN.md](07_TRADING_PLAN.md) | Trading methodology, rules, and edge definition |
| [EVENT_SOURCING.md](EVENT_SOURCING.md) | Event sourcing for trading operations |

## Core Components

1. **LLM Integration (The Brain)**
   - Tiered PydanticAI agents (Scout/Haiku → Analyst/Sonnet → Trader/Opus)
   - Structured decision output with validation firewall
   - Confidence calibration for statistical accuracy tracking
   - Context with order flow data (funding, OI, liquidations)

2. **Binance API Integration (The Spine)**
   - Real-time WebSocket data streams
   - Order flow data fetching (funding, OI, liquidations)
   - Dynamic risk management with volatility-aware sizing
   - Active position management (trailing, scaling, partials)

3. **Trading Engine**
   - Producer-Consumer async architecture
   - Pre-trade filters (liquidity, news, funding, confluence)
   - Technical indicators + order flow analysis
   - Event sourcing for audit trail and confidence calibration

4. **System Management**
   - Command-line interface for operations
   - Configuration management
   - Logging and monitoring

## Technology Stack

### Core Technologies

- **Python 3.13+**: Main programming language
- **Docker**: Containerization
- **Redis**: Cache and message queue
- **YAML**: Configuration format

### Key Libraries

- **python-binance**: Binance API client
- **pydantic-ai**: LLM agent framework with type safety
- **anthropic**: Anthropic Claude API client
- **jinja2**: Prompt template engine
- **Pandas/NumPy**: Data manipulation
- **pandas-ta**: Technical analysis indicators
- **Click**: CLI framework
- **Pytest**: Testing framework
- **pydantic**: Data validation and settings management
- **redis-py**: Redis client for caching and queues
- **asyncpg/SQLAlchemy**: PostgreSQL for event store
- **websockets**: WebSocket client for real-time data
- **PyYAML**: YAML parsing

## Project Structure

```
kavzitrader/
├── kavzi_trader/
│   ├── api/                   # API connectors
│   │   ├── binance/           # Binance API implementation
│   │   └── common/            # Common API interfaces
│   ├── cli/                   # Command line interfaces
│   │   └── commands/          # CLI command groups
│   ├── commons/               # Shared utilities
│   └── config/                # Configuration management
├── config/                    # Configuration files
│   └── config.yaml            # Main configuration file
├── docker/                    # Docker files
├── tests/                     # Test suite
└── docs/                      # Documentation
```

## Configuration System

KavziTrader uses environment variables and YAML configuration for flexible settings management.

### Configuration Structure

```
config/
└── config.yaml                # Main configuration file
```

### Configuration Example

```yaml
# config/config.yaml

# System settings
system:
  data_dir: "data/"
  models_dir: "models/"
  results_dir: "results/"
  timezone: "UTC"

# API credentials
api:
  binance:
    api_key: ${oc.env:BINANCE_API_KEY,""}
    api_secret: ${oc.env:BINANCE_API_SECRET,""}
    testnet: true

# Trading configuration
trading:
  symbols: [BTCUSDT, ETHUSDT]
  interval: "15m"
  max_positions: 2

# Dynamic risk management
risk:
  max_risk_percent: 1.0
  min_rr_ratio: 1.5
  max_drawdown_percent: 5.0
  pause_new_entries_drawdown: 3.0
  volatility_adjustments:
    HIGH: 0.5
    EXTREME: 0.25

# Position management
position_management:
  trailing_stop_atr_multiplier: 1.5
  break_even_trigger_atr: 1.0
  partial_exit_at_percent: 0.5
  partial_exit_size: 0.3
  max_hold_time_hours: 24
```

### Environment Variables

Set the following environment variables for configuration:

```bash
# Binance API
export KT_BINANCE_API_KEY="your_api_key"
export KT_BINANCE_API_SECRET="your_api_secret"
export KT_BINANCE_TESTNET="true"

# System
export KT_DATA_DIR="data/"
export KT_MODELS_DIR="models/"
export KT_RESULTS_DIR="results/"
export KT_TIMEZONE="UTC"
export KT_LOG_LEVEL="INFO"
```

## CLI Command Structure

```
kavzitrader
├── data
│   └── (data management commands)
├── model
│   └── status      # Show status of LLM connections
├── trade
│   └── (trading commands)
├── system
│   └── (system management commands)
└── config
    └── (configuration commands)
```

### CLI Examples

```bash
# Check system status
kavzitrader system

# Check model/LLM status
kavzitrader model status

# View configuration
kavzitrader config
```

## Development Best Practices

1. **Version Control**
   - Git-flow workflow
   - Feature branches
   - Pull request reviews

2. **Testing**
   - Unit tests for core components
   - Integration tests for pipelines

3. **Documentation**
   - Docstrings for all functions
   - README files for major components

4. **Code Quality**
   - Type hints
   - Linting (ruff)
   - CI/CD pipeline

## Docker Setup

The platform uses Docker for containerization. Start the services with:

```bash
cd docker
docker-compose up -d
```

This starts:
- Redis for caching and message queue

## Risk Management

1. **Position Sizing**
   - Risk-based position sizing
   - Maximum position limits

2. **Stop-Loss Strategy**
   - Volatility-based stops
   - Time-based stops

3. **Portfolio Management**
   - Asset diversification
   - Drawdown management

## Future Enhancements

1. **Advanced Features**
   - Multi-exchange support
   - Adaptive risk management
   - Market regime detection

2. **User Interface**
   - Web dashboard
   - Mobile alerts
   - Performance visualization

## Getting Started

1. Clone the repository
2. Install dependencies: `uv sync`
3. Set environment variables
4. Start Docker services: `cd docker && docker-compose up -d`
5. Run the CLI: `uv run kavzitrader --help`
