"""
AITBC Configuration Module
Hierarchical configuration with validation
"""

from typing import TypeAlias

from .hierarchical_config import (
    HierarchicalConfig,
    create_config_template,
)

try:
    from .hierarchical_config import ValidatedAITBCConfig, load_config

    BaseAITBCConfig: TypeAlias = ValidatedAITBCConfig
except ImportError:
    ValidatedAITBCConfig = None  # type: ignore[misc,assignment]
    BaseAITBCConfig: TypeAlias = HierarchicalConfig  # type: ignore[misc,assignment]
    load_config = None  # type: ignore[misc,assignment]

# Import legacy config classes from sibling config.py module
# (accessible only via importlib since package shadows the module)
try:
    import importlib.util
    import os

    _config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.py")
    _spec = importlib.util.spec_from_file_location("aitbc._legacy_config", _config_path)
    if _spec and _spec.loader:
        _legacy_config = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_legacy_config)
        AITBCConfig = _legacy_config.AITBCConfig
        if BaseAITBCConfig is HierarchicalConfig:
            BaseAITBCConfig = _legacy_config.BaseAITBCConfig  # type: ignore[misc]
except Exception:
    AITBCConfig = None  # type: ignore[misc,assignment]

__all__ = [
    "HierarchicalConfig",
    "ValidatedAITBCConfig",
    "BaseAITBCConfig",
    "AITBCConfig",
    "load_config",
    "create_config_template",
]
