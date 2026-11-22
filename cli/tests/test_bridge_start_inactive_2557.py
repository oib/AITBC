"""#2557: `aitbc bridge start` must exit non-zero when the service is not
active after the post-start check — 'Bridge Started' + exit 0 on a dead
service was a lie.
"""

from __future__ import annotations

import time

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.bridge import _service
from aitbc_cli.commands.bridge._service import start


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    monkeypatch.setattr(_service, "_systemctl", lambda action: (True, ""))
    return monkeypatch


def test_start_inactive_exits_nonzero(patched):
    patched.setattr(
        _service,
        "_event_bridge_status",
        lambda: {"status": "unreachable (ConnectError)", "bridge_status": "inactive"},
    )
    r = CliRunner().invoke(start, [], obj={})
    assert r.exit_code != 0
    assert "did not come up" in r.output
    assert "unreachable" in r.output
    assert "Bridge Started" not in r.output


def test_start_active_exits_zero(patched):
    patched.setattr(
        _service,
        "_event_bridge_status",
        lambda: {"status": "ok", "bridge_status": "active"},
    )
    r = CliRunner().invoke(start, [], obj={})
    assert r.exit_code == 0, r.output
    assert "Bridge Started" in r.output


def test_start_systemctl_failure_still_aborts(patched):
    patched.setattr(_service, "_systemctl", lambda action: (False, "Unit not found"))
    r = CliRunner().invoke(start, [], obj={})
    assert r.exit_code != 0
    assert "Failed to start" in r.output
