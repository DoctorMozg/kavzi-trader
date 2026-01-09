# KavziTrader

LLM-Based Crypto Trading Platform for Binance

## Overview

KavziTrader is an algorithmic trading platform designed for cryptocurrency trading on Binance. The platform implements a **Brain-Spine Architecture** that leverages Large Language Models (LLMs) for intelligent market analysis while maintaining deterministic, real-time execution.

**Key Architectural Concepts:**
- **The Brain**: Tiered PydanticAI agents (Haiku → Sonnet → Opus) for cost-optimized reasoning
- **The Spine**: High-speed async execution with dynamic risk and position management
- **Order Flow Edge**: Funding rates, OI, and liquidation levels for informed decisions
- **Validation Firewall**: Multi-layer safety with confidence calibration

## Features

- **Tiered LLM Agents**: Cost-optimized analysis (90%+ filter rate with cheap Scout)
- **Order Flow Analysis**: Funding rates, OI changes, liquidation level detection
- **Dynamic Risk**: Volatility-aware position sizing with ATR-based stops
- **Active Position Management**: Trailing stops, break-even, partial exits, scaling
- **Paper Trading**: Simulate trading without risking real assets
- **Confidence Calibration**: Statistical tracking of LLM decision accuracy

## Project Structure

```
kavzitrader/
├── kavzi_trader/           # Source code
│   ├── api/                # API connectors
│   ├── cli/                # Command line interfaces
│   ├── commons/            # Shared utilities
│   └── config/             # Configuration management
├── config/                 # Configuration files
├── tests/                  # Test suite
└── docs/                   # Documentation
```

## Installation

### Prerequisites

- Python 3.13+
- Redis (for caching)

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/kavzitrader.git
   cd kavzitrader
   ```

2. Install dependencies using uv:
   ```
   uv sync
   ```

3. Set up environment variables:
   ```
   cp .env.example .env
   # Edit .env with your Binance API keys
   ```

4. Start Docker services:
   ```
   cd docker && docker-compose up -d
   ```

## Usage

### CLI Commands

```bash
# View available commands
uv run kavzitrader --help

# Check system status
uv run kavzitrader system

# Check model/LLM status
uv run kavzitrader model status
```

## Documentation

For detailed documentation, see:

| Document | Description |
|----------|-------------|
| [Initial Setup](docs/01_INITIAL_SETUP.md) | Project overview and configuration |
| [Architecture](docs/02_ARCHITECTURE.md) | System architecture (Brain-Spine paradigm) |
| [LLM Architecture](docs/03_LLM_ARCHITECTURE.md) | Tiered agents with Jinja2 prompts |
| [Coding Standards](docs/04_CODING_STANDARDS.md) | Code style and best practices |
| [Implementation Plan](docs/05_IMPLEMENTATION_PLAN.md) | Phased development roadmap (20 weeks) |
| [Spine Implementation](docs/06_SPINE_IMPLEMENTATION.md) | Dynamic risk, position management |
| [Trading Plan](docs/07_TRADING_PLAN.md) | Trading methodology and edge definition |
| [Event Sourcing](docs/EVENT_SOURCING.md) | Audit trail and state management |

## Disclaimer

Trading cryptocurrencies involves significant risk. This software is for educational and research purposes only. Always use paper trading before deploying with real assets.
