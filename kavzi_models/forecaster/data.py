"""
Time series data preparation for the forecaster model.

This module handles data loading, preprocessing, feature engineering,
and dataset creation for the price movement forecasting model.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import torch
from sqlalchemy import text
from torch.utils.data import DataLoader, Dataset, random_split

from kavzi_models.common.database import Database
from kavzi_models.common.dataset import TimeSeriesDataset, create_data_loader
from kavzi_models.forecaster.config import DataConfig, ForecasterConfig

logger = logging.getLogger(__name__)


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical indicators to price data.
    
    Args:
        df: DataFrame with OHLCV data
        
    Returns:
        DataFrame with added technical indicators
    """
    # Make a copy to avoid modifying the original
    result = df.copy()
    
    # Relative Strength Index (RSI)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    
    rs = avg_gain / avg_loss.where(avg_loss != 0, 1)
    result['rsi'] = 100 - (100 / (1 + rs))
    
    # Moving Average Convergence Divergence (MACD)
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    result['macd'] = ema12 - ema26
    result['macd_signal'] = result['macd'].ewm(span=9, adjust=False).mean()
    result['macd_hist'] = result['macd'] - result['macd_signal']
    
    # Bollinger Bands
    sma20 = df['close'].rolling(window=20).mean()
    std20 = df['close'].rolling(window=20).std()
    result['bb_upper'] = sma20 + (std20 * 2)
    result['bb_middle'] = sma20
    result['bb_lower'] = sma20 - (std20 * 2)
    
    # Average True Range (ATR)
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift(1)).abs()
    low_close = (df['low'] - df['close'].shift(1)).abs()
    
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    result['atr'] = true_range.rolling(window=14).mean()
    
    # Average Directional Index (ADX)
    plus_dm = (df['high'].diff().where(df['high'].diff() > 0, 0) > 
               -df['low'].diff().where(df['low'].diff() < 0, 0)).astype(int) * df['high'].diff()
    minus_dm = (-df['low'].diff().where(df['low'].diff() < 0, 0) > 
                df['high'].diff().where(df['high'].diff() > 0, 0)).astype(int) * -df['low'].diff()
    
    plus_di = 100 * (plus_dm.rolling(window=14).mean() / result['atr'])
    minus_di = 100 * (minus_dm.rolling(window=14).mean() / result['atr'])
    
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).where((plus_di + minus_di) != 0, 1))
    result['adx'] = dx.rolling(window=14).mean()
    
    # Fill NaN values (resulting from rolling windows)
    result.fillna(method='bfill', inplace=True)
    result.fillna(0, inplace=True)
    
    return result


def calculate_returns(
    df: pd.DataFrame, 
    column: str = 'close', 
    periods: List[int] = [1, 5, 20]
) -> pd.DataFrame:
    """
    Calculate returns over different time periods.
    
    Args:
        df: DataFrame with price data
        column: Column to calculate returns for
        periods: List of periods to calculate returns for
        
    Returns:
        DataFrame with added return columns
    """
    result = df.copy()
    
    for period in periods:
        # Percentage change
        result[f'return_{period}'] = df[column].pct_change(periods=period)
        
        # Log returns
        result[f'log_return_{period}'] = np.log(df[column] / df[column].shift(period))
    
    # Fill NaN values
    result.fillna(0, inplace=True)
    
    return result


def normalize_dataframe(
    df: pd.DataFrame, 
    columns: List[str],
    method: str = 'zscore',
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    """
    Normalize specified columns in a DataFrame.
    
    Args:
        df: DataFrame to normalize
        columns: Columns to normalize
        method: Normalization method ('zscore' or 'minmax')
        
    Returns:
        Tuple of (normalized DataFrame, normalization parameters)
    """
    result = df.copy()
    params = {}
    
    for col in columns:
        if col not in df.columns:
            logger.warning(f"Column {col} not found in DataFrame")
            continue
            
        if method == 'zscore':
            mean = df[col].mean()
            std = df[col].std()
            if std == 0:  # Avoid division by zero
                std = 1e-8
            
            result[col] = (df[col] - mean) / std
            params[col] = {'mean': mean, 'std': std}
            
        elif method == 'minmax':
            min_val = df[col].min()
            max_val = df[col].max()
            if max_val == min_val:  # Avoid division by zero
                result[col] = 0
            else:
                result[col] = (df[col] - min_val) / (max_val - min_val)
            params[col] = {'min': min_val, 'max': max_val}
            
        else:
            raise ValueError(f"Unknown normalization method: {method}")
    
    return result, params


def prepare_time_series_data(
    df: pd.DataFrame, 
    config: DataConfig,
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, float]]]:
    """
    Prepare time series data for the forecaster model.
    
    Args:
        df: DataFrame with raw price data
        config: Data configuration
        
    Returns:
        Tuple of (processed DataFrame, normalization parameters)
    """
    # Ensure data is sorted by timestamp
    df = df.sort_index()
    
    # Add technical indicators if needed
    if any(i in config.technical_indicators for i in ["rsi", "macd", "bb_upper", "atr", "adx"]):
        df = add_technical_indicators(df)
    
    # Calculate returns if forecasting returns
    if config.target_column.startswith('return_') or config.target_column.startswith('log_return_'):
        df = calculate_returns(df)
    
    # Select features to use
    all_features = config.price_features.copy()
    all_features.extend(config.technical_indicators)
    
    # Add returns as features if calculated
    return_features = [col for col in df.columns if col.startswith('return_') or col.startswith('log_return_')]
    all_features.extend(return_features)
    
    # Make sure no duplicates and all features exist
    all_features = list(set(all_features))
    all_features = [f for f in all_features if f in df.columns]
    
    # Normalize features
    df_norm, norm_params = normalize_dataframe(
        df, 
        all_features,
        method=config.normalization_method,
    )
    
    return df_norm, norm_params


def create_target(
    df: pd.DataFrame, 
    target_column: str, 
    forecast_horizon: int,
) -> np.ndarray:
    """
    Create target variable for forecasting.
    
    Args:
        df: DataFrame with processed data
        target_column: Column to use as target
        forecast_horizon: Number of steps ahead to predict
        
    Returns:
        NumPy array with target values
    """
    if target_column not in df.columns:
        raise ValueError(f"Target column {target_column} not found in DataFrame")
    
    # Shift the target column by -forecast_horizon to align with current features
    targets = df[target_column].shift(-forecast_horizon).values
    
    # Remove trailing NaN values caused by the shift
    targets = targets[:-forecast_horizon] if forecast_horizon > 0 else targets
    
    return targets


class ForecasterDataset(TimeSeriesDataset):
    """
    Dataset for the forecaster model.
    
    This class handles loading and preprocessing of time series data
    for price movement forecasting.
    """
    
    def __init__(
        self,
        df: pd.DataFrame,
        config: DataConfig,
        targets: Optional[np.ndarray] = None,
        transform: Optional[callable] = None,
        target_transform: Optional[callable] = None,
    ) -> None:
        """
        Initialize the forecaster dataset.
        
        Args:
            df: DataFrame with time series data
            config: Data configuration
            targets: Optional pre-computed targets
            transform: Optional transform to apply to features
            target_transform: Optional transform to apply to targets
        """
        super().__init__(
            window_size=config.window_size,
            stride=config.stride,
            transform=transform,
            target_transform=target_transform,
        )
        
        self.df = df
        self.config = config
        
        # Set up features and targets
        self._load_data(targets)
    
    def _load_data(self, targets: Optional[np.ndarray] = None) -> None:
        """
        Load data for the dataset.
        
        Args:
            targets: Optional pre-computed targets
        """
        # Get feature columns
        all_features = self.config.price_features.copy()
        all_features.extend(self.config.technical_indicators)
        
        # Add returns as features if they exist
        return_features = [col for col in self.df.columns if col.startswith('return_') or col.startswith('log_return_')]
        all_features.extend(return_features)
        
        # Make sure all features exist in the dataframe
        all_features = [f for f in all_features if f in self.df.columns]
        
        # Convert features to numpy array
        self.data = self.df[all_features].values
        
        # Create sliding windows for features
        self.features = self._create_windows(self.data)
        
        # Create or use provided targets
        if targets is None:
            targets = create_target(
                self.df, 
                self.config.target_column, 
                self.config.forecast_horizon,
            )
        
        # Adjust targets to match feature windows
        # Each window corresponds to a single target value
        window_end_indices = np.arange(
            self.window_size - 1, 
            self.window_size - 1 + len(self.features),
            self.stride,
        )
        
        # Ensure we don't exceed the length of targets
        valid_indices = window_end_indices[window_end_indices < len(targets)]
        self.features = self.features[:len(valid_indices)]
        
        self.targets = targets[valid_indices].reshape(-1, 1)
        
        # Set length
        self._length = len(self.features)


def load_price_data_from_db(
    db: Database,
    symbol: str,
    interval: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Load OHLCV price data from database.
    
    Args:
        db: Database instance
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        interval: Timeframe interval (e.g., '1h', '1d')
        start_date: Optional start date (ISO format)
        end_date: Optional end date (ISO format)
        limit: Optional limit on number of rows
        
    Returns:
        DataFrame with OHLCV data
    """
    with db.session_scope() as session:
        # Build query conditions
        conditions = [
            f"symbol = '{symbol}'",
            f"interval = '{interval}'",
        ]
        
        if start_date:
            conditions.append(f"timestamp >= '{start_date}'")
        if end_date:
            conditions.append(f"timestamp <= '{end_date}'")
        
        # Combine conditions
        where_clause = " AND ".join(conditions)
        
        # Build the full query
        query = f"""
            SELECT 
                timestamp, opened as open, high, low, closed as close, volume
            FROM 
                market_data
            WHERE 
                {where_clause}
            ORDER BY 
                timestamp ASC
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        # Execute query
        result = session.execute(text(query))
        
        # Convert to DataFrame
        df = pd.DataFrame(result.fetchall())
        
        # Set column names if we got results
        if not df.empty:
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df.set_index('timestamp', inplace=True)
        
        return df


def create_train_val_test_split(
    dataset: Dataset,
    val_size: float = 0.15,
    test_size: float = 0.15,
    time_based: bool = True,
    seed: int = 42,
) -> Tuple[Dataset, Dataset, Dataset]:
    """
    Split dataset into train, validation, and test sets.
    
    Args:
        dataset: The dataset to split
        val_size: Validation set size as fraction of total
        test_size: Test set size as fraction of total
        time_based: Whether to use time-based splitting
        seed: Random seed for reproducibility
        
    Returns:
        Tuple of (train_dataset, val_dataset, test_dataset)
    """
    total_size = len(dataset)
    test_len = int(total_size * test_size)
    val_len = int(total_size * val_size)
    train_len = total_size - val_len - test_len
    
    if time_based:
        # For time series, respect temporal order
        train_dataset = torch.utils.data.Subset(dataset, range(0, train_len))
        val_dataset = torch.utils.data.Subset(dataset, range(train_len, train_len + val_len))
        test_dataset = torch.utils.data.Subset(dataset, range(train_len + val_len, total_size))
    else:
        # Random splitting
        generator = torch.Generator().manual_seed(seed)
        train_dataset, val_dataset, test_dataset = random_split(
            dataset, 
            [train_len, val_len, test_len],
            generator=generator,
        )
    
    return train_dataset, val_dataset, test_dataset


def prepare_forecaster_data(
    config: ForecasterConfig,
    db: Database,
    symbol: str,
    interval: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Union[DataLoader, Dict]]:
    """
    Complete pipeline to prepare data for the forecaster model.
    
    Args:
        config: Forecaster configuration
        db: Database instance
        symbol: Trading pair symbol
        interval: Timeframe interval
        start_date: Optional start date
        end_date: Optional end date
        
    Returns:
        Dictionary with data loaders and metadata
    """
    # Load raw price data
    logger.info(f"Loading price data for {symbol} ({interval})")
    df = load_price_data_from_db(
        db=db,
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
    )
    
    if df.empty:
        raise ValueError(f"No data found for {symbol} ({interval})")
    
    logger.info(f"Loaded {len(df)} rows of price data")
    
    # Prepare time series data
    logger.info("Preparing time series data")
    df_processed, norm_params = prepare_time_series_data(df, config.data)
    
    # Create dataset
    dataset = ForecasterDataset(df_processed, config.data)
    logger.info(f"Created dataset with {len(dataset)} samples")
    
    # Split into train, validation, and test sets
    train_dataset, val_dataset, test_dataset = create_train_val_test_split(
        dataset,
        val_size=config.data.val_size,
        test_size=config.data.test_size,
        time_based=config.data.time_based_split,
        seed=config.seed,
    )
    
    logger.info(f"Split dataset into {len(train_dataset)} train, {len(val_dataset)} validation, and {len(test_dataset)} test samples")
    
    # Create data loaders
    train_loader = create_data_loader(
        train_dataset,
        batch_size=config.training.batch_size,
        shuffle=True,
    )
    
    val_loader = create_data_loader(
        val_dataset,
        batch_size=config.training.batch_size,
        shuffle=False,
    )
    
    test_loader = create_data_loader(
        test_dataset,
        batch_size=config.training.batch_size,
        shuffle=False,
    )
    
    # Store the whole pipeline output
    result = {
        "train_loader": train_loader,
        "val_loader": val_loader,
        "test_loader": test_loader,
        "norm_params": norm_params,
        "feature_names": list(df_processed.columns),
        "n_features": len(list(df_processed.columns)),
        "dataset_meta": {
            "symbol": symbol,
            "interval": interval,
            "start_date": df.index.min(),
            "end_date": df.index.max(),
            "n_samples": len(dataset),
        }
    }
    
    return result 