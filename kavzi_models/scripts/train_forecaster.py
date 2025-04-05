#!/usr/bin/env python
"""
Training script for the forecaster model.

This script runs the complete pipeline to train and evaluate
the time series forecaster model for price prediction.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Optional

import hydra
import torch
from omegaconf import DictConfig

from kavzi_models.common.database import initialize_database
from kavzi_models.forecaster.config import ForecasterConfig, get_config
from kavzi_models.forecaster.data import prepare_forecaster_data
from kavzi_models.forecaster.model import create_forecaster_model
from kavzi_models.forecaster.trainer import train_forecaster
from kavzi_trader.commons.logging import setup_logging

logger = logging.getLogger(__name__)


@hydra.main(version_base=None, config_path="../../kavzi_models/conf", config_name="forecaster")
def main(cfg: DictConfig) -> None:
    """
    Main function to train the forecaster model.
    
    Args:
        cfg: Hydra configuration
    """
    # Set up logging
    setup_logging(log_level="INFO")
    logger.info("Starting forecaster model training")
    
    # Set random seed for reproducibility
    torch.manual_seed(cfg.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(cfg.seed)
    
    # Initialize configuration
    config = ForecasterConfig.model_validate(cfg)
    config.initialize_directories()
    
    # Initialize database connection
    db = initialize_database(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        database=os.environ.get("DB_NAME", "kavzitrader"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "postgres"),
    )
    
    # Prepare data for training
    symbol = cfg.get("symbol", "BTCUSDT")
    interval = cfg.get("interval", "1h")
    
    logger.info(f"Preparing data for {symbol} ({interval})")
    data_dict = prepare_forecaster_data(
        config=config,
        db=db,
        symbol=symbol,
        interval=interval,
        start_date=cfg.get("start_date"),
        end_date=cfg.get("end_date"),
    )
    
    # Create model
    logger.info("Creating forecaster model")
    model = create_forecaster_model(
        config=config,
        input_dim=data_dict["n_features"],
    )
    
    # Train model
    logger.info("Starting training")
    trained_model, results = train_forecaster(
        config=config,
        model=model,
        train_loader=data_dict["train_loader"],
        val_loader=data_dict["val_loader"],
        test_loader=data_dict["test_loader"],
    )
    
    # Log training results
    logger.info(f"Training completed. Best validation loss: {results['best_val_loss']:.6f}")
    logger.info(f"Trained for {results['epochs_trained']} epochs")
    logger.info(f"Final model saved to {results['final_model_path']}")
    
    # Log test metrics if available
    if results["test_metrics"]:
        logger.info(f"Test loss: {results['test_metrics']['loss']:.6f}")
        logger.info(f"Test directional accuracy: {results['test_metrics']['dir_accuracy']:.4f}")
        logger.info(f"Test profit factor: {results['test_metrics']['profit_factor']:.4f}")
    
    logger.info("Done!")


if __name__ == "__main__":
    main() 