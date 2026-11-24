"""AUDIT-EDGE pin: #2802 ipfs pin pre-flight bound."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_task_services as ats  # noqa: E402
import ipfs_pinning_sweeper as sweeper  # noqa: E402


# --- #2802: bounded pre-flight before pin/add ---


def test_exec_ipfs_refuses_oversize_before_pin(monkeypatch):
    """cat probe exceeding the cap must refuse WITHOUT calling pin/add."""
    calls = []

    class _Resp:
        status_code = 200

        def iter_content(self, n):
            yield b"x" * (2 * 1024 * 1024)

        def close(self):
            pass

    def fake_post(url, **kw):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(ats.requests, "post", fake_post)
    monkeypatch.setattr(ats, "_task_max_payload_bytes", lambda: 1024)
    with pytest.raises(ValueError, match="cap"):
        ats._exec_ipfs({"payload_ref": "Qm" + "a" * 44}, b"")
    assert not any("pin/add" in u for u in calls), calls


def test_ipfs_object_size_parses_dag_stat_stream():
    text = '{"TotalSize": 100}\n{"TotalSize": 5242880}\n{"TotalSize": 5242880}\n'
    assert ats._last_total_size(text) == 5242880
    assert sweeper._object_size.__doc__ is not None  # sanity: helper exists


def test_sweeper_object_size_uses_dag_stat(monkeypatch):
    seen = {}

    class _Resp:
        status_code = 200
        text = '{"TotalSize": 1}\n{"TotalSize": 777}\n'

    def fake_post(path, **kw):
        seen["path"] = path
        return _Resp()

    monkeypatch.setattr(sweeper, "_ipfs_post", fake_post)
    assert sweeper._object_size("Qm" + "b" * 44) == 777
    assert seen["path"] == "/api/v0/dag/stat"


def test_cat_within_cap_bounds_stream(monkeypatch):
    class _Resp:
        status_code = 200

        def iter_content(self, n):
            yield b"y" * 100
            yield b"z" * 100

        def close(self):
            pass

    monkeypatch.setattr(sweeper.requests, "post", lambda *a, **k: _Resp())
    monkeypatch.setattr(sweeper, "IPFS_API_URL", "http://127.0.0.1:5002")
    assert sweeper._cat_within_cap("Qm" + "c" * 44, 150) is False
    assert sweeper._cat_within_cap("Qm" + "c" * 44, 500) is True
