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

    # Set up sys.modules for proper package resolution
    # core/ is a sibling of aitbc_cli/, but imports reference it as aitbc_cli.core
    # We need to register these in sys.modules before loading core/main.py
    import importlib.util
    from pathlib import Path
    
    cli_dir = Path(__file__).parent
    core_dir = cli_dir.parent / "core"
    
    # Register aitbc_cli.core as a module pointing to the core/ directory
    if "aitbc_cli.core" not in sys.modules:
        core_spec = importlib.util.spec_from_file_location("aitbc_cli.core", core_dir / "__init__.py")
        if core_spec and core_spec.loader:
            core_module = importlib.util.module_from_spec(core_spec)
            sys.modules["aitbc_cli.core"] = core_module
    
    # Load core/main.py and register it as aitbc_cli.core.main
    cli_path = core_dir / "main.py"
    spec = importlib.util.spec_from_file_location("aitbc_cli.core.main", cli_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load modular CLI entrypoint from {cli_path}")
    
    module = importlib.util.module_from_spec(spec)
    sys.modules["aitbc_cli.core.main"] = module
    spec.loader.exec_module(module)
    
    value = module.cli if name == "cli" else module.main
    globals()[name] = value
    return value
