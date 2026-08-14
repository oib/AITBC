"""Unit tests for v0.16.1 Agent B tasks."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]


def _coordinator_module(module_path: str) -> ModuleType:
    """Import a coordinator-api module by adding its source directory to path."""
    src = str(REPO_ROOT / "apps" / "coordinator-api" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    return __import__(module_path, fromlist=["__name__"])


def test_env_validator_detects_missing_keys() -> None:
    from cli.aitbc_cli.services.env_validator import validate_env

    result = validate_env({})
    assert result.valid is False
    assert "AITBC_API_KEY" in result.missing


def test_hello_agent_example() -> None:
    import importlib.util

    main_path = REPO_ROOT / "examples" / "builder" / "hello-agent" / "main.py"
    spec = importlib.util.spec_from_file_location("hello_agent_main", str(main_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.run_agent()
    assert result["status"] == "ok"
    assert "AITBC" in result["message"]
