#!/usr/bin/env python3
"""Compatibility wrapper for the AITBC CLI entrypoint."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CLI_DIR))

# Ensure we don't pick up hermes-agent's cli module
hermes_cli_path = "/usr/local/lib/hermes-agent"
if hermes_cli_path in sys.path:
    sys.path.remove(hermes_cli_path)

from aitbc.constants import BLOCKCHAIN_RPC_PORT

DEFAULT_RPC_URL = f"http://localhost:{BLOCKCHAIN_RPC_PORT}"
_CLI_MODULE: ModuleType | None = None


def _load_cli_module() -> ModuleType:
    global _CLI_MODULE
    if _CLI_MODULE is not None:
        return _CLI_MODULE

    cli_path = Path(__file__).parent / "aitbc_cli" / "core" / "main.py"
    spec = importlib.util.spec_from_file_location("aitbc_cli_core_main", cli_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load modular CLI entrypoint from {cli_path}")

    module = importlib.util.module_from_spec(spec)
    # Register module in sys.modules with proper package name for import resolution
    sys.modules["aitbc_cli.core.main"] = module
    spec.loader.exec_module(module)
    _CLI_MODULE = module
    return module


def main(argv=None):
    return _load_cli_module().main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
