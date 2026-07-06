"""
AITBC Configuration Module
Hierarchical configuration with validation
"""

from .hierarchical_config import (
    HierarchicalConfig,
    create_config_template,
)

try:
    from .hierarchical_config import AITBCConfig, ValidatedAITBCConfig, load_config

    # Backward compatibility alias — BaseAITBCConfig was the old name in config.py
    BaseAITBCConfig: type = ValidatedAITBCConfig
except ImportError:
    AITBCConfig = None  # type: ignore[assignment,misc]
    ValidatedAITBCConfig = None  # type: ignore[assignment,misc]
    BaseAITBCConfig = HierarchicalConfig
    load_config = None  # type: ignore[assignment]

__all__ = [
    "AITBCConfig",
    "BaseAITBCConfig",
    "HierarchicalConfig",
    "ValidatedAITBCConfig",
    "create_config_template",
    "load_config",
]
