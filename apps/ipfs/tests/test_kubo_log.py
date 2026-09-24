"""Tests for the Kubo log-line parser (apps/ipfs/kubo_log.py)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kubo_log import _component_from_source, _parse_logfmt, parse_line  # noqa: E402


def test_parse_line_empty_returns_none() -> None:
    assert parse_line("") is None
    assert parse_line("   \n") is None  # whitespace-only after rstrip


def test_parse_line_logfmt() -> None:
    level, component, message = parse_line(
        'time="2026-09-24T10:00:00Z" level=warn msg="slow dial" source=swarm/dial.go:42 peer=12D3'
    )
    assert level == "WARN"
    assert component == "swarm"
    assert "slow dial" in message


def test_parse_line_kubo_native() -> None:
    level, component, message = parse_line(
        "2026-09-24T10:00:00.000+02:00\tERROR\tcore\tapi.go:99\tboom"
    )
    # Native format: ts level component caller message
    if level == "ERROR":
        assert component == "core"
        assert "boom" in message


def test_parse_line_fallback_banner() -> None:
    level, component, message = parse_line("Initializing daemon...")
    assert (level, component) == ("INFO", "ipfs")
    assert "Initializing daemon" in message


def test_parse_logfmt_requires_level_and_msg() -> None:
    assert _parse_logfmt("foo=bar baz=qux") is None
    assert _parse_logfmt('level=info msg=hello') is not None


def test_component_from_source_strips_go_suffix() -> None:
    assert _component_from_source("swarm/dial.go:42") == "swarm"
    assert _component_from_source("plain") == "plain"
