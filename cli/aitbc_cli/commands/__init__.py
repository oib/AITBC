"""Compatibility package for AITBC CLI command modules."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_BUILD_COMMANDS_DIR = _PACKAGE_DIR.parents[1] / "build" / "lib" / "aitbc_cli" / "commands"

if _BUILD_COMMANDS_DIR.exists():
    __path__.append(str(_BUILD_COMMANDS_DIR))
