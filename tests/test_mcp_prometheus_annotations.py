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


# GAP-MCP-ALERTS-WATCH-1 (#309): ``aitbc_prometheus_alerts`` carried these
# watch-mode options under read_only_hint — ``watch`` loops forever,
# ``notify_urls`` POSTs webhooks, ``alert_log_path``/``metrics_file``
# append/write files. The generated tool is a one-shot read; the watcher
# runs as a systemd unit through the CLI. This fails if any of them
# return to a read-only tool's signature.
_WATCH_FAMILY = {
    "watch",
    "interval",
    "emit",
    "alert_log_path",
    "notify_urls",
    "notify_format",
    "notify_topic",
    "notify_click",
    "notify_min_severity",
    "silence_file",
    "remind_interval",
    "metrics_file",
}


def test_read_only_tools_expose_no_watch_or_write_options():
    for name, (ann, sig) in _tools().items():
        if "read_only_hint=True" not in ann:
            continue
        params = set(re.findall(r"^    (\w+):", sig, re.MULTILINE))
        leaked = params & _WATCH_FAMILY
        assert not leaked, f"{name}: watch/notify/write options on a read-only tool: {sorted(leaked)}"
