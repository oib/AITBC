"""_compose_explain reads its parameter, not the fastapi.status module (APP-28).

`match.py` imports `status` from fastapi. `_compose_explain` took a `miner_status`
parameter but read the bare name `status`, which resolved to that module import. A module
object is always truthy, so the `if status else` guard always took the first branch and
raised AttributeError -- 'module starlette.status has no attribute queue_len' -- on every
/v1/match call that reached candidate building. The surrounding broad except turned it
into a generic 500, so it read as a server fault rather than a name collision.

The v0.22 audit ledger recorded this as "could not be located; match.py appears to have
been renamed or merged". The file and the defect were both still there.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from poolhub.app.routers.match import _compose_explain


def test_uses_the_supplied_status():
    miner_status = SimpleNamespace(queue_len=3, avg_latency_ms=42)

    explain = _compose_explain(0.87, miner=None, miner_status=miner_status)

    assert "load=3" in explain
    assert "latency=42" in explain


def test_handles_a_missing_status():
    explain = _compose_explain(0.5, miner=None, miner_status=None)

    assert "load=0" in explain
    assert "latency=n/a" in explain


def test_reports_the_score():
    explain = _compose_explain(0.87654, miner=None, miner_status=None)

    assert "score=0.877" in explain


@pytest.mark.parametrize("queue_len", [0, 1, 99])
def test_reads_queue_len_from_the_parameter(queue_len: int):
    """A distinct value per case: reading the module would give the same wrong answer."""
    miner_status = SimpleNamespace(queue_len=queue_len, avg_latency_ms=10)

    assert f"load={queue_len}" in _compose_explain(0.5, miner=None, miner_status=miner_status)


def test_does_not_touch_the_fastapi_status_module():
    """Guards the exact regression: the module has no queue_len, so reading it raises."""
    from poolhub.app.routers import match

    assert not hasattr(match.status, "queue_len"), "test premise: fastapi.status has no queue_len"

    # Would raise AttributeError if _compose_explain reached for the module.
    _compose_explain(0.5, miner=None, miner_status=SimpleNamespace(queue_len=7, avg_latency_ms=1))
