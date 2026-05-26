"""AITBC CLI package compatibility surface."""

from __future__ import annotations

from importlib import import_module
import sys

__version__ = "0.1.0"
__author__ = "AITBC Team"
__email__ = "team@aitbc.net"

# Provide compatibility aliases for source-tree imports used by modular commands.
# Note: core and models are sibling directories, not subpackages of aitbc_cli
# These compatibility aliases are disabled to prevent sys.modules corruption
# if "aitbc_cli.core" not in sys.modules:
#     sys.modules["aitbc_cli.core"] = import_module("aitbc_cli.core")
# if "aitbc_cli.models" not in sys.modules:
#     sys.modules["aitbc_cli.models"] = import_module("aitbc_cli.models")
# Note: aitbc_cli.config is imported normally to avoid circular import issues

__all__ = ["cli", "main"]


def __getattr__(name: str):
    """Lazily expose the modular CLI entrypoints."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    # Load core/main.py directly via spec_from_file_location to avoid package resolution issues
    import importlib.util
    from pathlib import Path
    
    cli_path = Path(__file__).parent.parent / "core" / "main.py"
    spec = importlib.util.spec_from_file_location("aitbc_cli_core_main", cli_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load modular CLI entrypoint from {cli_path}")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    value = module.cli if name == "cli" else module.main
    globals()[name] = value
    return value
