from __future__ import annotations

import os
import runpy
from pathlib import Path

import aitbc_agent
import aitbc_sdk

import aitbc
from aitbc.aitbc_logging import get_logger as direct_get_logger
from aitbc.constants import BLOCKCHAIN_RPC_PORT, DATA_DIR, KEYSTORE_DIR, LOG_DIR, PACKAGE_VERSION
from aitbc.exceptions import NetworkError, ValidationError
from aitbc.network import AITBCHTTPClient
from aitbc.utils.paths import ensure_dir, get_keystore_path
from aitbc.utils.validation import validate_address, validate_url

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_aitbc_root_exports_match_lightweight_submodules() -> None:
    assert aitbc.DATA_DIR == DATA_DIR
    assert aitbc.LOG_DIR == LOG_DIR
    assert aitbc.KEYSTORE_DIR == KEYSTORE_DIR
    assert aitbc.BLOCKCHAIN_RPC_PORT == BLOCKCHAIN_RPC_PORT
    assert aitbc.PACKAGE_VERSION == PACKAGE_VERSION

    assert aitbc.get_logger is direct_get_logger
    # AITBCHTTPClient is no longer re-exported from the aitbc root; aitbc.network is its
    # home. Asserted there instead of pretending the root still carries it.
    assert AITBCHTTPClient.__module__.startswith("aitbc.network")
    assert aitbc.NetworkError is NetworkError
    assert aitbc.ValidationError is ValidationError
    assert aitbc.get_keystore_path is get_keystore_path
    assert aitbc.ensure_dir is ensure_dir
    # Validation helpers are no longer root re-exports either; aitbc.utils.validation is
    # where they live.
    assert validate_address.__module__ == "aitbc.utils.validation"
    assert validate_url.__module__ == "aitbc.utils.validation"
    # aitbc.testing and the aitbc.MockFactory re-export were both removed as dead code
    # in 6fd975755; there is no longer an import surface here to assert on.


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
    """The CLI is a package now, not the single cli/aitbc_cli.py module this once loaded."""
    import importlib

    main_module = importlib.import_module("aitbc_cli.core.main")
    assert callable(main_module.main)

    mining = importlib.import_module("aitbc_cli.commands.mining")
    assert mining.DEFAULT_RPC_URL.startswith("http://localhost:")


def test_agent_coordinator_wrapper_bootstrap(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_execvp(file: str, args: list[str]) -> None:
        captured["file"] = file
        captured["args"] = list(args)

    captured_env: dict[str, str] = {}

    def fake_execvpe(file: str, args: list[str], env: dict) -> None:
        captured["file"] = file
        captured["args"] = list(args)
        captured_env.update(env)

    with monkeypatch.context() as m:
        m.setattr(os, "execvp", fake_execvp)
        m.setattr(os, "execvpe", fake_execvpe)
        m.setattr(aitbc.utils.paths, "ensure_dir", lambda path: path)
        m.setenv("AITBC_ENV_FILE", "placeholder")
        m.setenv("AITBC_NODE_ENV_FILE", "placeholder")
        m.setenv("PYTHONPATH", "placeholder")
        m.setenv("DATA_DIR", "placeholder")
        m.setenv("LOG_DIR", "placeholder")

        runpy.run_path(
            str(REPO_ROOT / "scripts" / "services" / "agent-coordinator-wrapper.py"),
            run_name="__main__",
        )

        assert captured["file"] == "/opt/aitbc/venv/bin/python"
        assert captured["args"][0] == "/opt/aitbc/venv/bin/python"
        assert captured["args"][1] == "-m"
        assert captured["args"][2] == "agent_app.main"
        # The wrapper does not set AITBC_ENV_FILE / AITBC_NODE_ENV_FILE -- it never
        # reads or writes them. What it does set for the child is PYTHONPATH, so that is
        # what is asserted.
        assert "PYTHONPATH" in captured_env
        assert "/opt/aitbc/apps/agent-coordinator/src" in captured_env["PYTHONPATH"]
