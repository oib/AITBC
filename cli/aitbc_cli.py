#!/usr/bin/env python3
"""Compatibility wrapper for the AITBC CLI entrypoint."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from aitbc.constants import BLOCKCHAIN_RPC_PORT

DEFAULT_RPC_URL = f"http://localhost:{BLOCKCHAIN_RPC_PORT}"
_LEGACY_MODULE: ModuleType | None = None


def _load_legacy_module() -> ModuleType:
    global _LEGACY_MODULE
    if _LEGACY_MODULE is not None:
        return _LEGACY_MODULE

    legacy_path = Path(__file__).with_name("aitbc_cli.legacy.py")
    spec = importlib.util.spec_from_file_location("aitbc_cli_legacy", legacy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load legacy CLI entrypoint from {legacy_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _LEGACY_MODULE = module
    return module


def main(argv=None):
    return _load_legacy_module().main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
