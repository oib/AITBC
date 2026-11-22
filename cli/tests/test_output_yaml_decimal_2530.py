"""#2530: output(..., 'yaml') must render Decimal/datetime/Path payloads the
same way the json format does (default=str), not raise RepresenterError.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from aitbc_cli.utils.output import _render


def test_yaml_renders_decimal_datetime_path():
    payload = {
        "amount": Decimal("1.25"),
        "when": datetime(2026, 1, 1, tzinfo=UTC),
        "path": Path("/tmp/x"),
        "nested": {"n": Decimal("0.5")},
    }
    out = _render(payload, "yaml")
    assert "1.25" in out
    assert "2026-01-01" in out
    assert "/tmp/x" in out


def test_yaml_matches_json_semantics():
    payload = {"a": Decimal("2"), "b": [Decimal("3")]}
    assert json.loads(_render(payload, "json"))["a"] == "2"
    y = _render(payload, "yaml")
    assert "a: '2'" in y or 'a: "2"' in y or "a: 2" in y
