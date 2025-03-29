"""
Data validation for historical market data.

This module provides functionality for validating market data,
including checks for sequence continuity, outliers, and data integrity.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
from pydantic import ValidationError

from src.api.binance.constants import KLINE_INTERVALS
from src.api.common.models import CandlestickSchema
from src.data.collection.config.schemas import DataValidationConfigSchema

logger = logging.getLogger(__name__)


class DataValidator:
    """
    Validates and cleans market data.
    
    This class:
    1. Checks data for anomalies
    2. Validates sequence continuity
    3. Identifies outliers
    4. Generates validation reports
    """
    
    def __init__(self, config: Optional[DataValidationConfigSchema] = None):
        """
        Initialize the data validator.
        
        Args:
            config: Optional configuration for data validation
        """
        self.config = config or DataValidationConfigSchema()
    
    def validate_candlesticks(
        self, 
        candlesticks: List[CandlestickSchema],
        symbol: str,
        interval: str
    ) -> Dict[str, Any]:
        """
        Validate a list of candlesticks.
        
        Args:
            candlesticks: List of candlestick data
            symbol: Trading pair symbol
            interval: Timeframe interval
            
        Returns:
            Validation report with statistics and issues
        """
        if not candlesticks:
            return {
                "valid": True,
                "total": 0,
                "issues": [],
                "warnings": [],
                "stats": {}
            }
        
        # Sort candlesticks by timestamp
        sorted_candles = sorted(candlesticks, key=lambda x: x.open_time)
        
        # Initialize report
        report = {
            "valid": True,
            "total": len(sorted_candles),
            "issues": [],
            "warnings": [],
            "stats": {}
        }
        
        # Validate sequence continuity if enabled
        if self.config.check_sequence:
            sequence_issues = self._check_sequence_continuity(sorted_candles, interval)
            if sequence_issues:
                report["issues"].extend(sequence_issues)
                report["valid"] = False
        
        # Check for outliers if enabled
        if self.config.check_outliers:
            outliers = self._detect_outliers(sorted_candles)
            if outliers:
                report["warnings"].extend(outliers)
        
        # Check for minimum volume if specified
        if self.config.min_volume > 0:
            volume_issues = [
                f"Low volume at {c.open_time}: {c.volume}"
                for c in sorted_candles if float(c.volume) < self.config.min_volume
            ]
            if volume_issues:
                report["warnings"].extend(volume_issues)
        
        # Calculate basic statistics
        report["stats"] = self._calculate_statistics(sorted_candles)
        
        return report
    
    def _check_sequence_continuity(
        self, 
        candlesticks: List[CandlestickSchema],
        interval: str
    ) -> List[str]:
        """
        Check for gaps in the candlestick sequence.
        
        Args:
            candlesticks: Sorted list of candlesticks
            interval: Timeframe interval
            
        Returns:
            List of continuity issues
        """
        if len(candlesticks) < 2:
            return []  # Not enough data to check continuity
        
        # Get the interval in milliseconds
        interval_ms = KLINE_INTERVALS.get(interval, 60) * 1000
        expected_gap = timedelta(milliseconds=interval_ms)
        
        issues = []
        for i in range(1, len(candlesticks)):
            curr_time = candlesticks[i].open_time
            prev_time = candlesticks[i-1].open_time
            actual_gap = curr_time - prev_time
            
            # Calculate the gap as a percentage of the expected interval
            gap_percent = (actual_gap.total_seconds() / expected_gap.total_seconds() - 1) * 100
            
            if gap_percent > self.config.max_gap_percent:
                issues.append(
                    f"Sequence gap of {actual_gap} between {prev_time} and {curr_time} "
                    f"(expected {expected_gap})"
                )
        
        return issues
    
    def _detect_outliers(
        self, 
        candlesticks: List[CandlestickSchema]
    ) -> List[str]:
        """
        Detect outliers in candlestick data.
        
        Args:
            candlesticks: Sorted list of candlesticks
            
        Returns:
            List of outlier descriptions
        """
        if len(candlesticks) < 10:  # Need enough data for meaningful detection
            return []
        
        # Extract price and volume data
        prices = [
            {
                'open': float(c.open),
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close)
            } 
            for c in candlesticks
        ]
        volumes = [float(c.volume) for c in candlesticks]
        timestamps = [c.open_time for c in candlesticks]
        
        # Create DataFrames for analysis
        df_price = pd.DataFrame(prices)
        df_price['timestamp'] = timestamps
        df_volume = pd.DataFrame({
            'volume': volumes,
            'timestamp': timestamps
        })
        
        outliers = []
        
        # Price outlier detection using Z-score
        for col in ['open', 'high', 'low', 'close']:
            z_scores = np.abs((df_price[col] - df_price[col].mean()) / df_price[col].std())
            outlier_indices = np.where(z_scores > self.config.outlier_std_threshold)[0]
            
            for idx in outlier_indices:
                outliers.append(
                    f"Price outlier ({col}): {df_price[col].iloc[idx]} at {df_price['timestamp'].iloc[idx]} "
                    f"(z-score: {z_scores.iloc[idx]:.2f})"
                )
        
        # Volume outlier detection
        z_scores = np.abs((df_volume['volume'] - df_volume['volume'].mean()) / df_volume['volume'].std())
        outlier_indices = np.where(z_scores > self.config.outlier_std_threshold)[0]
        
        for idx in outlier_indices:
            outliers.append(
                f"Volume outlier: {df_volume['volume'].iloc[idx]} at {df_volume['timestamp'].iloc[idx]} "
                f"(z-score: {z_scores.iloc[idx]:.2f})"
            )
        
        return outliers
    
    def _calculate_statistics(
        self, 
        candlesticks: List[CandlestickSchema]
    ) -> Dict[str, Any]:
        """
        Calculate statistics from candlestick data.
        
        Args:
            candlesticks: List of candlesticks
            
        Returns:
            Dictionary of statistics
        """
        if not candlesticks:
            return {}
        
        # Extract basic fields
        opens = [float(c.open) for c in candlesticks]
        highs = [float(c.high) for c in candlesticks]
        lows = [float(c.low) for c in candlesticks]
        closes = [float(c.close) for c in candlesticks]
        volumes = [float(c.volume) for c in candlesticks]
        
        stats = {
            "start_time": candlesticks[0].open_time,
            "end_time": candlesticks[-1].open_time,
            "count": len(candlesticks),
            "price": {
                "min": min(lows),
                "max": max(highs),
                "avg": np.mean(closes),
                "std": np.std(closes),
                "first": opens[0],
                "last": closes[-1],
                "change": closes[-1] - opens[0],
                "change_percent": (closes[-1] - opens[0]) / opens[0] * 100 if opens[0] != 0 else 0
            },
            "volume": {
                "total": sum(volumes),
                "avg": np.mean(volumes),
                "min": min(volumes),
                "max": max(volumes),
                "std": np.std(volumes)
            }
        }
        
        return stats 