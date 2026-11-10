"""#1482: the monitoring wrapper must not hardcode ``--host 0.0.0.0``.

The dashboard is unauthenticated (service topology, per-service health
detail, host CPU/memory/disk/network metrics). ``main.py`` and the
shipped ``aitbc-monitoring.service`` unit both bind ``127.0.0.1``; the
wrapper's hardcoded ``0.0.0.0`` would publish the surface to every host
that can route to :8002 if the wrapper were ever used. The fix defaults
to loopback and honours ``BIND_HOST`` for a deliberate off-host bind.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[1] / "aitbc-monitoring-wrapper.py"


def _load_wrapper():
    spec = importlib.util.spec_from_file_location("monitoring_wrapper", WRAPPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("BIND_HOST", "LOG_LEVEL", "ACCESS_LOG"):
        monkeypatch.delenv(name, raising=False)


class TestWrapperBuildCmd:
    def test_default_binds_loopback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        cmd = _load_wrapper().build_cmd()
        assert cmd[cmd.index("--host") + 1] == "127.0.0.1"
        assert cmd[cmd.index("--port") + 1] == "8002"

    def test_bind_host_env_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        monkeypatch.setenv("BIND_HOST", "10.1.223.136")
        cmd = _load_wrapper().build_cmd()
        assert cmd[cmd.index("--host") + 1] == "10.1.223.136"

    def test_no_wildcard_bind(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear(monkeypatch)
        cmd = _load_wrapper().build_cmd()
        assert "0.0.0.0" not in cmd

    def test_import_does_not_exec(self) -> None:
        # If the module executed os.execvp at import, this process would be gone.
        assert hasattr(_load_wrapper(), "build_cmd")
