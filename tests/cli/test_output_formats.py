"""``--format`` must actually change the rendering.

Until 2026-09-15 ``output()`` had a single branch for structured data, commented
"Table format -- just JSON for now". ``OUTPUT_FORMAT_OPTION`` advertises
``table|json|yaml|csv`` on roughly every command in the CLI, so three of the four
choices were accepted and silently ignored.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from aitbc_cli.utils.output import _render

ROWS = [
    {"id": "offer-a", "price": 5},
    {"id": "offer-b", "price": 7, "extra": "x"},
]
FLAT = {"height": 42, "chain": "aitbc1", "ok": True}
NESTED = {"chain": {"height": 42}}


def test_table_renders_a_grid_not_json():
    rendered = _render(ROWS, "table")
    assert rendered.startswith("+")
    assert "offer-a" in rendered
    with pytest.raises(json.JSONDecodeError):
        json.loads(rendered)


def test_table_of_a_flat_mapping_is_field_value():
    rendered = _render(FLAT, "table")
    assert "Field" in rendered and "Value" in rendered
    assert "aitbc1" in rendered


def test_csv_is_parseable_and_keeps_ragged_rows_aligned():
    parsed = list(csv.DictReader(io.StringIO(_render(ROWS, "csv"))))
    assert [r["id"] for r in parsed] == ["offer-a", "offer-b"]
    # "extra" exists on the second row only; the first must still be padded.
    assert parsed[0]["extra"] == ""
    assert parsed[1]["extra"] == "x"


def test_yaml_is_yaml_not_json():
    yaml = pytest.importorskip("yaml")
    rendered = _render(ROWS, "yaml")
    assert not rendered.lstrip().startswith("[")
    assert yaml.safe_load(rendered) == ROWS


def test_json_is_unchanged():
    assert _render(ROWS, "json") == json.dumps(ROWS, indent=2)
    assert _render(NESTED, "json") == json.dumps(NESTED, indent=2)


def test_nested_data_falls_back_to_json_in_every_tabular_format():
    # A nested structure has no columns; JSON is the only faithful rendering,
    # and that is what table/csv must produce rather than inventing one.
    for fmt in ("table", "csv"):
        assert json.loads(_render(NESTED, fmt)) == NESTED


def test_strings_pass_through_untouched(capsys):
    from aitbc_cli.utils.output import output

    # ~8 call sites pre-serialize with output(json.dumps(...)); they must not be
    # re-rendered or re-wrapped.
    payload = json.dumps({"a": 1}, indent=2)
    output(payload, "table")
    assert capsys.readouterr().out.rstrip("\n") == payload


def test_machine_readable_formats_suppress_the_title(capsys):
    from aitbc_cli.utils.output import output

    output(FLAT, "csv", title="Offers")
    assert "Offers" not in capsys.readouterr().out
    output(FLAT, "table", title="Offers")
    assert "Offers" in capsys.readouterr().out
