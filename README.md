# KavziTrader

LLM-Based Crypto Trading Platform for Binance

## Overview

KavziTrader is an algorithmic trading platform designed for cryptocurrency trading on Binance. The platform implements a **Brain-Spine Architecture** that leverages Large Language Models (LLMs) for intelligent market analysis while maintaining deterministic, real-time execution.

**Key Architectural Concepts:**
- **The Brain**: PydanticAI agent with Claude Opus for probabilistic reasoning
- **The Spine**: High-speed async execution layer for real-time operations
- **Validation Firewall**: Multi-layer safety system preventing invalid trades

## Features

- **LLM Integration**: Use LLMs for market analysis and trading decisions
- **Binance API Integration**: Real-time market data and trading execution
- **Risk Management**: Comprehensive risk controls and position sizing
- **Paper Trading**: Simulate trading without risking real assets
- **Live Trading**: Execute trades on Binance with real assets
- **Visualization**: Comprehensive charts and performance metrics

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
| [LLM Architecture](docs/03_LLM_ARCHITECTURE.md) | LLM integration with PydanticAI + Jinja2 |
| [Coding Standards](docs/04_CODING_STANDARDS.md) | Code style and best practices |
| [Implementation Plan](docs/05_IMPLEMENTATION_PLAN.md) | Phased development roadmap |
| [Spine Implementation](docs/06_SPINE_IMPLEMENTATION.md) | Execution layer, events, and queues |
| [Event Sourcing](docs/EVENT_SOURCING.md) | Audit trail and state management |

## Disclaimer

Trading cryptocurrencies involves significant risk. This software is for educational and research purposes only. Always use paper trading before deploying with real assets.
