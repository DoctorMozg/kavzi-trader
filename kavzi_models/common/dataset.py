"""
Base dataset utilities for model training.

This module provides base classes for creating PyTorch datasets
and data loading utilities for the models.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader

from kavzi_trader.commons.time_utility import utc_now

logger = logging.getLogger(__name__)


class BaseDataset(Dataset, ABC):
    """
    Base class for all datasets in the models package.
    
    This abstract base class defines the interface for datasets
    and provides common functionality.
    """
    
    def __init__(
        self,
        transform: Optional[Callable] = None,
        target_transform: Optional[Callable] = None,
    ) -> None:
        """
        Initialize the base dataset.
        
        Args:
            transform: Optional transform to be applied to features
            target_transform: Optional transform to be applied to targets
        """
        self.transform = transform
        self.target_transform = target_transform
        self._length = 0
        
    @abstractmethod
    def _load_data(self) -> None:
        """
        Load the data for the dataset.
        
        This method should be implemented by subclasses to load
        the specific data needed for the dataset.
        """
        pass
    
    @abstractmethod
    def __getitem__(self, idx: int) -> Tuple[Any, Any]:
        """
        Get a sample from the dataset.
        
        Args:
            idx: Index of the sample to get
            
        Returns:
            Tuple of (features, target)
        """
        pass
    
    def __len__(self) -> int:
        """
        Get the length of the dataset.
        
        Returns:
            Number of samples in the dataset
        """
        return self._length


class TimeSeriesDataset(BaseDataset):
    """
    Base class for time series datasets.
    
    This class provides common functionality for time series data,
    including windowing and feature normalization.
    """
    
    def __init__(
        self,
        window_size: int,
        stride: int = 1,
        transform: Optional[Callable] = None,
        target_transform: Optional[Callable] = None,
    ) -> None:
        """
        Initialize the time series dataset.
        
        Args:
            window_size: Size of the sliding window for sequences
            stride: Step size between windows
            transform: Optional transform to be applied to features
            target_transform: Optional transform to be applied to targets
        """
        super().__init__(transform, target_transform)
        self.window_size = window_size
        self.stride = stride
        self.data: Optional[pd.DataFrame] = None
        self.features: Optional[np.ndarray] = None
        self.targets: Optional[np.ndarray] = None
    
    def _create_windows(self, data: np.ndarray) -> np.ndarray:
        """
        Create sliding windows from data.
        
        Args:
            data: Input data array
            
        Returns:
            Array of windowed data
        """
        # Calculate number of windows
        n_samples = data.shape[0]
        n_windows = (n_samples - self.window_size) // self.stride + 1
        
        # Create empty array for windows
        windows = np.zeros((n_windows, self.window_size, data.shape[1]))
        
        # Fill windows
        for i in range(n_windows):
            start_idx = i * self.stride
            end_idx = start_idx + self.window_size
            windows[i] = data[start_idx:end_idx]
        
        return windows
    
    def _normalize_features(
        self, 
        features: np.ndarray,
        method: str = "zscore",
    ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """
        Normalize features using specified method.
        
        Args:
            features: Feature array to normalize
            method: Normalization method ('zscore' or 'minmax')
            
        Returns:
            Tuple of (normalized features, normalization params)
        """
        if method == "zscore":
            # Calculate mean and std for each feature
            mean = np.mean(features, axis=0)
            std = np.std(features, axis=0)
            std = np.where(std == 0, 1e-8, std)  # Prevent division by zero
            
            # Normalize
            normalized = (features - mean) / std
            params = {"mean": mean, "std": std}
            
        elif method == "minmax":
            # Calculate min and max for each feature
            min_vals = np.min(features, axis=0)
            max_vals = np.max(features, axis=0)
            range_vals = max_vals - min_vals
            range_vals = np.where(range_vals == 0, 1e-8, range_vals)  # Prevent division by zero
            
            # Normalize
            normalized = (features - min_vals) / range_vals
            params = {"min": min_vals, "max": max_vals}
            
        else:
            raise ValueError(f"Unknown normalization method: {method}")
        
        return normalized, params
    
    def save_dataset(self, path: Path) -> None:
        """
        Save the dataset to disk.
        
        Args:
            path: Path to save the dataset
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        
        save_data = {
            "features": self.features,
            "targets": self.targets,
            "window_size": self.window_size,
            "stride": self.stride,
            "metadata": {
                "created_at": utc_now().isoformat(),
                "samples": len(self),
            }
        }
        
        # Save using numpy's compressed format
        np.savez_compressed(path, **save_data)
        logger.info(f"Dataset saved to {path}")
    
    @classmethod
    def load_dataset(
        cls,
        path: Path,
        transform: Optional[Callable] = None,
        target_transform: Optional[Callable] = None,
    ) -> "TimeSeriesDataset":
        """
        Load a dataset from disk.
        
        Args:
            path: Path to load the dataset from
            transform: Optional transform to be applied to features
            target_transform: Optional transform to be applied to targets
            
        Returns:
            Loaded TimeSeriesDataset
        """
        # Load the saved data
        data = np.load(path, allow_pickle=True)
        
        # Create a new dataset instance
        dataset = cls(
            window_size=int(data["window_size"]),
            stride=int(data["stride"]),
            transform=transform,
            target_transform=target_transform,
        )
        
        # Set the data attributes
        dataset.features = data["features"]
        dataset.targets = data["targets"]
        dataset._length = dataset.features.shape[0]
        
        logger.info(f"Dataset loaded from {path} with {dataset._length} samples")
        return dataset
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get a sample from the dataset.
        
        Args:
            idx: Index of the sample to get
            
        Returns:
            Tuple of (features, target)
        """
        if self.features is None or self.targets is None:
            raise RuntimeError("Dataset not initialized. Call _load_data() first.")
        
        # Get feature window and target
        feature = self.features[idx]
        target = self.targets[idx]
        
        # Apply transforms if provided
        if self.transform:
            feature = self.transform(feature)
        if self.target_transform:
            target = self.target_transform(target)
        
        # Convert to torch tensors
        feature_tensor = torch.tensor(feature, dtype=torch.float32)
        target_tensor = torch.tensor(target, dtype=torch.float32)
        
        return feature_tensor, target_tensor


def create_data_loader(
    dataset: Dataset,
    batch_size: int = 32,
    shuffle: bool = True,
    num_workers: int = 0,
    pin_memory: bool = True,
) -> DataLoader:
    """
    Create a PyTorch DataLoader from a dataset.
    
    Args:
        dataset: The dataset to create a DataLoader for
        batch_size: Number of samples in each batch
        shuffle: Whether to shuffle the dataset
        num_workers: Number of subprocesses for data loading
        pin_memory: Whether to pin memory for faster GPU transfer
        
    Returns:
        PyTorch DataLoader
    """
    return DataLoader(
        dataset=dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=pin_memory,
    ) 