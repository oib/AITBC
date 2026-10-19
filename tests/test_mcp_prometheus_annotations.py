"""Pin the annotation of every ``aitbc_prometheus_*`` MCP tool.

GAP-ALERTHIST-CONFIRM-1 (#304): ``aitbc_prometheus_alert_history`` sat
behind the mutating gate (``destructive_hint`` + ``dry_run``/``confirm``)
although it only reads the watcher's alert log — the tool the reset-day
watcher needs to call freely. Four siblings had the same defect:
``query``, ``rules``, ``series`` and ``targets`` are pure Prometheus GET
endpoints. This test fails if any ``aitbc_prometheus_*`` tool loses
``read_only_hint`` or regains the confirm gate.

The generated module is parsed as source text (the same style as
``cli/tests/test_reset_guard.py``) so the test needs no FastMCP import.
"""

from __future__ import annotations

import re
from pathlib import Path

GENERATED = Path(__file__).resolve().parent.parent / "mcp-server" / "aitbc_mcp_cli_tools_generated_prometheus.py"

# Every generated prometheus tool and its intended read_only_hint.
# ``alerts`` caveat: its generated signature still carries the watch-mode
# options (watch/notify_urls/alert_log_path) which can POST webhooks and
# append files when watch=True — a reported, separately-decided item. The
# pin records today's intended annotation; flipping it is a deliberate
# change this table makes visible.
EXPECTED: dict[str, bool] = {
    "aitbc_prometheus_alert_history": True,
    "aitbc_prometheus_alerts": True,
    "aitbc_prometheus_check": True,
    "aitbc_prometheus_metric": True,
    "aitbc_prometheus_query": True,
    "aitbc_prometheus_rules": True,
    "aitbc_prometheus_series": True,
    "aitbc_prometheus_targets": True,
}

_TOOL_RE = re.compile(
    r"@mcp\.tool\(annotations=ToolAnnotations\((?P<ann>[^)]*)\)\)\s*\n"
    r"def (?P<name>aitbc_prometheus_\w+)\((?P<sig>.*?)\) -> str:",
    re.DOTALL,
)


def _tools() -> dict[str, tuple[str, str]]:
    source = GENERATED.read_text()
    return {m.group("name"): (m.group("ann"), m.group("sig")) for m in _TOOL_RE.finditer(source)}


def test_every_prometheus_tool_is_discovered():
    found = _tools()
    assert set(found) == set(EXPECTED), (
        f"tool set drifted — expected {sorted(EXPECTED)}, found {sorted(found)}; "
        "update EXPECTED in the same commit that adds or removes a tool"
    )


def test_read_only_annotations():
    for name, (ann, _sig) in _tools().items():
        if EXPECTED[name]:
            assert "read_only_hint=True" in ann, f"{name}: lost read_only_hint ({ann!r})"
            assert "destructive_hint" not in ann, f"{name}: destructive_hint leaked back"
        else:
            assert "read_only_hint=True" not in ann, f"{name}: unexpectedly read-only ({ann!r})"


def test_no_confirm_gate_on_read_tools():
    """No prometheus tool may carry the dry_run/confirm mutating gate."""
    for name, (_ann, sig) in _tools().items():
        assert "confirm" not in sig, f"{name}: confirm parameter leaked back"
        assert "dry_run" not in sig, f"{name}: dry_run parameter leaked back"
