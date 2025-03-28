"""
Transformer model implementation for KavziTrader.

This module provides the Transformer architecture used for time series forecasting.
"""

import json
from pathlib import Path
from typing import ClassVar

import numpy as np
import torch
from numpy.typing import NDArray
from torch import nn, optim
from torch.utils.data import DataLoader, TensorDataset

from src.models.base.base_model import BaseNnModel
from src.models.config import TransformerConfigSchema
from src.models.metrics import TrainingMetricsSchema


class TransformerModel(BaseNnModel):
    """
    Transformer model for time series forecasting in KavziTrader.

    This model uses the Transformer architecture which has shown superior
    performance for sequential data compared to RNNs and CNNs, particularly
    for capturing long-range dependencies.
    """

    MODEL_TYPE: ClassVar[str] = "transformer"
    VERSION: ClassVar[str] = "1.0.0"

    def __init__(
        self,
        name: str,
        config: TransformerConfigSchema,
    ) -> None:
        """
        Initialize the Transformer model.

        Args:
            name: Unique name for this model instance
            config: Configuration parameters for the model
        """
        super().__init__(name, config)

        # Build model architecture
        self.model = self._build_model()
        self.criterion = nn.MSELoss()
        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=config.learning_rate,
        )

        # Set device
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu",
        )
        self.model.to(self.device)

    def _build_model(self) -> nn.Module:
        """
        Build the transformer model architecture.

        Returns:
            PyTorch transformer model
        """
        config = self.config
        return nn.Transformer(
            d_model=config.d_model,
            nhead=config.nhead,
            num_encoder_layers=config.num_encoder_layers,
            num_decoder_layers=config.num_decoder_layers,
            dim_feedforward=config.dim_feedforward,
            dropout=config.dropout,
            activation=config.activation,
            batch_first=True,
        )

    def train(
        self,
        features: NDArray[np.float32],
        targets: NDArray[np.float32],
    ) -> TrainingMetricsSchema:
        """
        Train the model on the provided data.

        Args:
            features: Array of feature vectors
            targets: Array of target values

        Returns:
            Training metrics
        """
        # Convert data to tensors (already numpy arrays)
        x = torch.tensor(features, dtype=torch.float32)
        y = torch.tensor(targets, dtype=torch.float32).view(-1, 1)

        # Create dataset and dataloader
        dataset = TensorDataset(x, y)
        batch_size = self.config.batch_size
        train_size = int((1 - self.config.validation_split) * len(dataset))
        val_size = len(dataset) - train_size
        train_dataset, val_dataset = torch.utils.data.random_split(
            dataset,
            [train_size, val_size],
        )
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        # Training loop
        epochs = self.config.epochs
        patience = self.config.patience
        best_val_loss = float("inf")
        patience_counter = 0

        # Initialize metrics schema
        metrics = TrainingMetricsSchema()  # type: ignore[call-arg]

        for _ in range(epochs):
            # Training phase
            self.model.train()
            train_loss = 0.0
            for x_batch, y_batch in train_loader:
                x_batch_local = x_batch.to(self.device)
                y_batch_local = y_batch.to(self.device)

                # Forward pass
                self.optimizer.zero_grad()
                outputs = self.model(x_batch_local, x_batch_local)
                loss = self.criterion(outputs, y_batch_local)

                # Backward pass and optimize
                loss.backward()
                self.optimizer.step()

                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validation phase
            self.model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for x_batch, y_batch in val_loader:
                    x_batch_local = x_batch.to(self.device)
                    y_batch_local = y_batch.to(self.device)

                    outputs = self.model(x_batch_local, x_batch_local)
                    loss = self.criterion(outputs, y_batch_local)
                    val_loss += loss.item()

            val_loss /= len(val_loader)

            # Update metrics for this epoch
            metrics.add_epoch_results(train_loss, val_loss)

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                # Save the best model
                self._save_checkpoint()
            else:
                patience_counter += 1
                if patience_counter >= patience and self.config.early_stopping:
                    metrics.early_stopped = True
                    break

        # Load the best model
        self._load_checkpoint()

        # Update model metrics
        self.update_metrics(metrics)
        return metrics

    def predict(self, features: NDArray[np.float32]) -> NDArray[np.float32]:
        """
        Generate predictions for the provided features.

        Args:
            features: Array of feature vectors

        Returns:
            Array of predicted values
        """
        self.model.eval()

        # Convert to tensor (already numpy array)
        x = torch.tensor(features, dtype=torch.float32).to(self.device)

        with torch.no_grad():
            predictions = self.model(x, x)

        # Convert to numpy array and return
        return predictions.cpu().numpy().flatten()

    def _save_checkpoint(self) -> None:
        """Save model checkpoint during training."""
        checkpoint_dir = Path(".checkpoints") / self.name
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
            },
            checkpoint_dir / "best_checkpoint.pt",
        )

    def _load_checkpoint(self) -> None:
        """Load model checkpoint during training."""
        checkpoint_dir = Path(".checkpoints") / self.name
        checkpoint_path = checkpoint_dir / "best_checkpoint.pt"

        if checkpoint_path.exists():
            checkpoint = torch.load(checkpoint_path)
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])

    def _save_model_specific(self, directory: Path) -> None:
        """
        Save model-specific data to disk.

        Args:
            directory: Directory to save model-specific data
        """
        path = directory / f"{self.name}_model.pt"
        torch.save(self.model.state_dict(), path)

    @classmethod
    def load(cls, directory: Path, name: str) -> "TransformerModel":
        """
        Load a model from disk.

        Args:
            directory: Directory where the model is saved
            name: Name of the model to load

        Returns:
            Loaded model instance
        """
        metadata_path = directory / f"{name}.json"
        model_path = directory / f"{name}_model.pt"

        with open(metadata_path) as f:
            metadata = json.load(f)

        # Create a new instance with proper configuration schema
        config = TransformerConfigSchema.model_validate(metadata["config"])
        model = cls(name=name, config=config)

        # Load metrics as schema
        metrics = TrainingMetricsSchema.model_validate(metadata["metrics"])
        model.metrics = metrics

        # Load model parameters
        model.model.load_state_dict(torch.load(model_path))

        return model
