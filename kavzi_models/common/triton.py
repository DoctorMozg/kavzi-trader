"""
Triton export utilities for models.

This module provides utilities for exporting models to Triton Inference Server.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class TritonModelExporter:
    """
    Export PyTorch models for Triton Inference Server.
    
    This class provides utilities for exporting PyTorch models
    to a format compatible with NVIDIA Triton Inference Server.
    """
    
    def __init__(
        self,
        model_name: str,
        model_version: int = 1,
        export_path: Optional[Path] = None,
    ) -> None:
        """
        Initialize the Triton model exporter.
        
        Args:
            model_name: Name of the model
            model_version: Version of the model
            export_path: Path to export the model to
        """
        self.model_name = model_name
        self.model_version = model_version
        
        # Default export path if none provided
        if export_path is None:
            export_path = Path("models") / "export" / "triton"
        self.export_path = export_path
        
        # Create model directory structure
        self.model_path = self.export_path / self.model_name / str(self.model_version)
        self.model_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Triton exporter initialized for model {model_name} (v{model_version})")
    
    def export_torchscript(
        self,
        model: nn.Module,
        example_inputs: Union[torch.Tensor, Tuple[torch.Tensor, ...]],
        input_names: List[str],
        output_names: List[str],
        dynamic_axes: Optional[Dict] = None,
    ) -> Path:
        """
        Export a PyTorch model to TorchScript format for Triton.
        
        Args:
            model: PyTorch model to export
            example_inputs: Example inputs for tracing
            input_names: Names of input tensors
            output_names: Names of output tensors
            dynamic_axes: Dictionary of dynamic axes
            
        Returns:
            Path to the exported model
        """
        # Create model file path
        model_file = self.model_path / "model.pt"
        
        # Set model to evaluation mode
        model.eval()
        
        # Trace the model with example inputs
        traced_model = torch.jit.trace(model, example_inputs)
        
        # Save the traced model
        torch.jit.save(traced_model, model_file)
        
        logger.info(f"Model exported to {model_file}")
        
        # Create config file
        self._create_config_file(input_names, output_names, dynamic_axes)
        
        return model_file
    
    def _create_config_file(
        self,
        input_names: List[str],
        output_names: List[str],
        dynamic_axes: Optional[Dict] = None,
    ) -> Path:
        """
        Create Triton model configuration file.
        
        Args:
            input_names: Names of input tensors
            output_names: Names of output tensors
            dynamic_axes: Dictionary of dynamic axes
            
        Returns:
            Path to the config file
        """
        config_path = self.model_path / "config.pbtxt"
        
        # Basic config
        config = [
            f'name: "{self.model_name}"',
            'backend: "pytorch"',
            'max_batch_size: 64',
        ]
        
        # Add inputs
        for idx, name in enumerate(input_names):
            input_config = [
                "input [",
                f'  name: "{name}"',
                '  data_type: TYPE_FP32',
                '  dims: [ -1 ]',  # Default to variable length
                "]",
            ]
            config.extend(input_config)
        
        # Add outputs
        for idx, name in enumerate(output_names):
            output_config = [
                "output [",
                f'  name: "{name}"',
                '  data_type: TYPE_FP32',
                '  dims: [ -1 ]',  # Default to variable length
                "]",
            ]
            config.extend(output_config)
        
        # Add instance group configuration for scaling
        instance_group = [
            "instance_group [",
            "  count: 1",
            '  kind: KIND_GPU',
            "]",
        ]
        config.extend(instance_group)
        
        # Write config to file
        with open(config_path, "w") as f:
            f.write("\n".join(config))
        
        logger.info(f"Triton config created at {config_path}")
        
        return config_path
    
    @staticmethod
    def validate_triton_model(model_path: Path) -> bool:
        """
        Validate that the exported model can be loaded.
        
        Args:
            model_path: Path to the exported model
            
        Returns:
            True if validation successful
        """
        try:
            # Try to load the model
            loaded_model = torch.jit.load(model_path)
            logger.info(f"Model at {model_path} loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Error validating model: {e}")
            return False 