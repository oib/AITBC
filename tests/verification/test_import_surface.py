from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ROOT / "packages" / "py" / "aitbc-agent-sdk" / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "py" / "aitbc-sdk" / "src"))

import aitbc
import aitbc_agent
import aitbc_sdk
import aitbc.paths as aitbc_paths

from aitbc.aitbc_logging import get_logger as direct_get_logger
from aitbc.constants import BLOCKCHAIN_RPC_PORT, DATA_DIR, ENV_FILE, KEYSTORE_DIR, LOG_DIR, NODE_ENV_FILE, PACKAGE_VERSION
from aitbc.exceptions import NetworkError, ValidationError
from aitbc.http_client import AITBCHTTPClient
from aitbc.paths import ensure_dir, get_keystore_path
from aitbc.testing import MockFactory
from aitbc.validation import validate_address, validate_url


def test_aitbc_root_exports_match_lightweight_submodules() -> None:
    assert aitbc.DATA_DIR == DATA_DIR
    assert aitbc.LOG_DIR == LOG_DIR
    assert aitbc.KEYSTORE_DIR == KEYSTORE_DIR
    assert aitbc.BLOCKCHAIN_RPC_PORT == BLOCKCHAIN_RPC_PORT
    assert aitbc.PACKAGE_VERSION == PACKAGE_VERSION

    assert aitbc.get_logger is direct_get_logger
    assert aitbc.AITBCHTTPClient is AITBCHTTPClient
    assert aitbc.NetworkError is NetworkError
    assert aitbc.ValidationError is ValidationError
    assert aitbc.get_keystore_path is get_keystore_path
    assert aitbc.ensure_dir is ensure_dir
    assert aitbc.validate_address is validate_address
    assert aitbc.validate_url is validate_url
    assert aitbc.MockFactory is MockFactory


def test_aitbc_agent_sdk_lazy_exports_resolve() -> None:
    assert hasattr(aitbc_agent, "Agent")
    assert hasattr(aitbc_agent, "AITBCAgent")
    assert hasattr(aitbc_agent, "ComputeProvider")
    assert hasattr(aitbc_agent, "ComputeConsumer")
    assert hasattr(aitbc_agent, "PlatformBuilder")
    assert hasattr(aitbc_agent, "SwarmCoordinator")


def test_aitbc_sdk_lazy_exports_resolve() -> None:
    assert hasattr(aitbc_sdk, "CoordinatorReceiptClient")
    assert hasattr(aitbc_sdk, "ReceiptPage")
    assert hasattr(aitbc_sdk, "ReceiptVerification")
    assert hasattr(aitbc_sdk, "SignatureValidation")
    assert hasattr(aitbc_sdk, "verify_receipt")
    assert hasattr(aitbc_sdk, "verify_receipts")


def test_cli_module_import_smoke() -> None:
    module_globals = runpy.run_path(str(REPO_ROOT / "cli" / "aitbc_cli.py"))
    assert "main" in module_globals
    assert module_globals["DEFAULT_RPC_URL"].startswith("http://localhost:")


def test_agent_coordinator_wrapper_bootstrap(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_execvp(file: str, args: list[str]) -> None:
        captured["file"] = file
        captured["args"] = list(args)

    with monkeypatch.context() as m:
        m.setattr(os, "execvp", fake_execvp)
        m.setattr(aitbc_paths, "ensure_dir", lambda path: path)
        m.setenv("AITBC_ENV_FILE", "placeholder")
        m.setenv("AITBC_NODE_ENV_FILE", "placeholder")
        m.setenv("PYTHONPATH", "placeholder")
        m.setenv("DATA_DIR", "placeholder")
        m.setenv("LOG_DIR", "placeholder")

        runpy.run_path(
            str(REPO_ROOT / "scripts" / "wrappers" / "aitbc-agent-coordinator-wrapper.py"),
            run_name="__main__",
        )

        assert captured["file"] == "/opt/aitbc/venv/bin/python"
        assert captured["args"][0] == "/opt/aitbc/venv/bin/python"
        assert captured["args"][1] == "-m"
        assert captured["args"][2] == "uvicorn"
        assert captured["args"][3] == "app.main:app"
        assert os.environ["AITBC_ENV_FILE"] == str(ENV_FILE)
        assert os.environ["AITBC_NODE_ENV_FILE"] == str(NODE_ENV_FILE)
