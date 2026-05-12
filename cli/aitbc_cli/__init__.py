"""AITBC CLI package compatibility surface."""

from __future__ import annotations

from importlib import import_module
import sys

__version__ = "0.1.0"
__author__ = "AITBC Team"
__email__ = "team@aitbc.net"

# Provide compatibility aliases for source-tree imports used by modular commands.
if "aitbc_cli.core" not in sys.modules:
    sys.modules["aitbc_cli.core"] = import_module("core")
if "aitbc_cli.models" not in sys.modules:
    sys.modules["aitbc_cli.models"] = import_module("models")
if "aitbc_cli.config" not in sys.modules:
    sys.modules["aitbc_cli.config"] = import_module("config")

__all__ = ["cli", "main"]


def __getattr__(name: str):
    """Lazily expose the modular CLI entrypoints."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module("cli.core.main")
    value = module.cli if name == "cli" else module.main
    globals()[name] = value
    return value
