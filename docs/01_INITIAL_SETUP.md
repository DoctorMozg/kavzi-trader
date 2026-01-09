# KavziTrader: LLM-Based Crypto Trading Platform

## Project Overview

KavziTrader is an automated trading platform designed to leverage Large Language Models (LLMs) for crypto trading on Binance. The platform implements a **Brain-Spine Architecture** that decouples cognitive reasoning (LLM) from deterministic execution, enabling sophisticated AI-driven trading while maintaining real-time market responsiveness.

## Documentation

| Document | Description |
|----------|-------------|
| [01_INITIAL_SETUP.md](01_INITIAL_SETUP.md) | This document - project overview and setup |
| [02_ARCHITECTURE.md](02_ARCHITECTURE.md) | System architecture and Brain-Spine paradigm |
| [03_LLM_ARCHITECTURE.md](03_LLM_ARCHITECTURE.md) | LLM integration with PydanticAI + Jinja2 prompts |
| [04_CODING_STANDARDS.md](04_CODING_STANDARDS.md) | Coding standards and best practices |
| [05_IMPLEMENTATION_PLAN.md](05_IMPLEMENTATION_PLAN.md) | Phased implementation roadmap |
| [06_SPINE_IMPLEMENTATION.md](06_SPINE_IMPLEMENTATION.md) | Execution layer, events, and queues |
| [EVENT_SOURCING.md](EVENT_SOURCING.md) | Event sourcing for trading operations |

## Core Components

1. **LLM Integration (The Brain)**
   - PydanticAI agent with Anthropic Claude Opus
   - Structured decision output with validation firewall
   - Chain-of-thought reasoning with confidence scoring
   - Context window engineering for optimal LLM performance

2. **Binance API Integration (The Spine)**
   - Real-time WebSocket data streams
   - Async order execution with OCO support
   - Account state monitoring and reconciliation
   - Historical data downloading for analysis

3. **Trading Engine**
   - Producer-Consumer async architecture
   - Risk validation with position limits
   - Technical indicator calculation
   - Event sourcing for audit trail

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
- **Pandas/NumPy**: Data manipulation
- **pandas-ta**: Technical analysis indicators
- **Click**: CLI framework
- **Pytest**: Testing framework
- **Plotly**: Data visualization
- **pydantic**: Data validation and settings management
- **fastapi**: API development
- **redis-py**: Redis client for caching and queues
- **asyncpg/SQLAlchemy**: PostgreSQL for event store
- **websockets**: WebSocket client for real-time data
- **python-dotenv**: Environment variable management
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

# API credentials - these will be overridden by environment variables
api:
  binance:
    api_key: ${oc.env:BINANCE_API_KEY,""}
    api_secret: ${oc.env:BINANCE_API_SECRET,""}
    testnet: true
    use_proxy: false

# Trading configuration
trading:
  symbols:              # Trading pairs to monitor
    - BTCUSDT
    - ETHUSDT
  interval: "15m"       # Candle interval for analysis
  max_positions: 2      # Max concurrent positions

# Risk management
risk:
  max_risk_percent: 1.0          # Max % of account per trade
  min_rr_ratio: 1.5              # Minimum risk/reward ratio
  max_drawdown_percent: 5.0      # Max drawdown before stopping
  max_position_size_percent: 10  # Max % of account per position
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
