"""P2P/RPC port resolution: the p2p wrapper honours P2P_BIND_PORT/HOST and
the multi-chain manager reads the documented *_BIND_PORT names.

Live-fleet basis (GAP-P2P-PORTS-1): only hub runs the
``aitbc-blockchain-p2p`` unit, listening on 127.0.0.1:7070 via the old
hardcode; ``P2P_BIND_PORT`` is set but unread on node1/node2 (inert). The
fix must default to 7070 so no live listener changes, and the MCM base
ports must come from ``RPC_BIND_PORT``/``P2P_BIND_PORT`` — the legacy
``RPC_PORT``/``P2P_PORT`` names appear in no live env file and are not
read back.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[1] / "aitbc-blockchain-p2p-wrapper.py"


def _load_wrapper():
    spec = importlib.util.spec_from_file_location("p2p_wrapper", WRAPPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("P2P_BIND_HOST", "P2P_BIND_PORT", "RPC_BIND_PORT", "RPC_PORT", "P2P_PORT"):
        monkeypatch.delenv(name, raising=False)


class TestWrapperBuildCmd:
    def test_defaults_match_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        cmd = _load_wrapper().build_cmd()
        assert cmd[cmd.index("--host") + 1] == "0.0.0.0"
        # 7070 is what the hardcode produced on the live hub — unchanged.
        assert cmd[cmd.index("--port") + 1] == "7070"
        assert cmd[-1] == "--access-log"

    def test_env_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("P2P_BIND_HOST", "127.0.0.1")
        monkeypatch.setenv("P2P_BIND_PORT", "8200")
        cmd = _load_wrapper().build_cmd()
        assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
        assert cmd[cmd.index("--port") + 1] == "8200"

    def test_import_does_not_exec(self) -> None:
        # If the module executed os.execvpe at import, this process would be gone.
        assert hasattr(_load_wrapper(), "build_cmd")


class TestBasePortsFromEnv:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        from aitbc_chain.network.multi_chain_manager import base_ports_from_env

        assert base_ports_from_env() == (8202, 7070)

    def test_bind_names_are_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("RPC_BIND_PORT", "8212")
        monkeypatch.setenv("P2P_BIND_PORT", "8200")
        from aitbc_chain.network.multi_chain_manager import base_ports_from_env

        assert base_ports_from_env() == (8212, 8200)

    def test_legacy_names_are_not_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # RPC_PORT/P2P_PORT exist in no live env file; they are not a fallback.
        _clear(monkeypatch)
        monkeypatch.setenv("RPC_PORT", "9999")
        monkeypatch.setenv("P2P_PORT", "9998")
        from aitbc_chain.network.multi_chain_manager import base_ports_from_env

        assert base_ports_from_env() == (8202, 7070)
