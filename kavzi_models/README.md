# KavziTrader Models Package

This package contains neural network models for trading predictions, sentiment analysis, and token embeddings.

## Package Structure

```
kavzi_models/
├── common/              # Common utilities
│   ├── database.py      # Synchronous database connector
│   ├── dataset.py       # Base dataset utilities
│   ├── metrics.py       # Evaluation metrics
│   └── triton.py        # Triton export utilities
├── conf/                # Hydra configuration files
│   └── forecaster.yaml  # Forecaster model configuration
├── embeddings/          # Token embedding models
├── sentiment/           # Sentiment analysis models
├── forecaster/          # Price forecasting models
│   ├── config.py        # Model configuration
│   ├── data.py          # Data preparation
│   ├── model.py         # Model architecture
│   └── trainer.py       # Training pipeline
├── inference/           # Inference utilities
└── scripts/             # Training and export scripts
    └── train_forecaster.py  # Forecaster training script
```

## Phase 1: Foundation

The initial phase establishes the foundation for model development:

1. Project structure setup
2. Database connector implementation
3. Dataset utilities implementation
4. Evaluation metrics
5. Triton export utilities

## Setup

This package requires the dependencies listed in the main project's `pyproject.toml`.

## Usage Example

```python
# Database connection
from kavzi_models.common.database import initialize_database

db = initialize_database(
    host="localhost",
    port=5432,
    database="kavzitrader",
    user="postgres",
    password="password",
)

# Creating a dataset
from kavzi_models.common.dataset import TimeSeriesDataset

# Metrics calculation
from kavzi_models.common.metrics import calculate_regression_metrics

# Export to Triton
from kavzi_models.common.triton import TritonModelExporter

# Training a forecaster model
# Run from the command line:
# python -m kavzi_models.scripts.train_forecaster

# Override configuration via command line:
# python -m kavzi_models.scripts.train_forecaster symbol=ETHUSDT interval=4h
```

## Future Development

Future phases will include:
1. Forecaster model development
2. Token embedding model
3. Sentiment analysis model
4. Integration of all models
5. Triton deployment 