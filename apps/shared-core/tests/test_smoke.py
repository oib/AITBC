"""Smoke tests for shared-core: the re-export shims must stay in sync with aitbc_shared."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def test_config_shim_reexports_aitbc_shared() -> None:
    import aitbc_shared
    from shared_core.core import config

    assert config.DatabaseConfig is aitbc_shared.DatabaseConfig
    assert config.ServiceSettings is aitbc_shared.ServiceSettings


def test_package_importable() -> None:
    import shared_core

    assert shared_core is not None


def test_database_module_importable() -> None:
    from shared_core.core import database

    assert database is not None


def test_security_package_importable() -> None:
    from shared_core.core import security

    assert security is not None
