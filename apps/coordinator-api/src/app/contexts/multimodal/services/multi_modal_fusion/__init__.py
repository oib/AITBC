"""
Multi-Modal Fusion Service - Modular Implementation
Service facade for backward compatibility with the original monolithic file

This module provides a modular structure for multi-modal fusion:
- neural_modules.py: PyTorch neural network components (CrossModalAttention, MultiModalTransformer, AdaptiveModalityWeighting)
- fusion_engine.py: Main MultiModalFusionEngine class for fusion operations

The original multi_modal_fusion.py has been deprecated in favor of this modular structure.
"""

from .neural_modules import CrossModalAttention, MultiModalTransformer, AdaptiveModalityWeighting
from .fusion_engine import MultiModalFusionEngine

__all__ = ['CrossModalAttention', 'MultiModalTransformer', 'AdaptiveModalityWeighting', 'MultiModalFusionEngine']
