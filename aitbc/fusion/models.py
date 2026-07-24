"""Data models for multi-modal fusion.

These types are shared between the coordinator-api fusion engine and any
future fusion consumers (edge GPU inference, agent protocols, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FusionStrategy(StrEnum):
    """Supported multi-modal fusion strategies."""

    ENSEMBLE = "ensemble_fusion"
    ATTENTION = "attention_fusion"
    CROSS_MODAL = "cross_modal_attention"
    TRANSFORMER = "transformer_fusion"
    GRAPH_NEURAL = "graph_neural_fusion"
    NEURAL_ARCHITECTURE_SEARCH = "neural_architecture_search"


@dataclass
class FusionInput:
    """A single modality payload for fusion."""

    modality: str  # text, image, audio, video, structured
    data: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FusionConfig:
    """Runtime configuration for a fusion operation."""

    strategy: FusionStrategy = FusionStrategy.ENSEMBLE
    embed_dim: int = 512
    num_layers: int = 6
    num_heads: int = 8
    learning_rate: float = 0.001
    batch_size: int = 32
    epochs: int = 100
    modality_weights: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class FusionOutput:
    """Result of a fusion operation."""

    fused_embedding: Any | None = None
    modality_weights: dict[str, float] = field(default_factory=dict)
    synergy_score: float = 0.0
    robustness_score: float = 0.0
    status: str = "ready"  # training, ready, deployed, deprecated
    logs: list[dict[str, Any]] = field(default_factory=list)
