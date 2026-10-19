"""``aitbc prometheus metric`` — raw read of ONE named metric from a node's own /metrics endpoint.

A canned exposition text stands in for the HTTP scrape (``prom.httpx.get`` is
mocked); no real endpoint is contacted. Values are fake counters, not node data.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import prometheus as prom

EXPOSITION = """# HELP v9_would_reject_total Shadow-rule rejections counted on this node.
# TYPE v9_would_reject_total counter
v9_would_reject_total{reason="not_at_parent"} 2
v9_would_reject_total{reason="bad_sig"} 0
v9_would_reject_total_bucket{le="0.5"} 5
v9_would_reject_total_bucket{le="+Inf"} 7
v9_would_reject_total_sum 12.5
v9_would_reject_total_count 7
other_metric 1e3
this line is malformed garbage
python_info{version="3.13.0"} 1
"""


@pytest.fixture
def runner():
    return CliRunner()


def _scrape(text: str = EXPOSITION, status: int = 200):
    response = mock.Mock()
    response.status_code = status
    response.text = text
    if status >= 400:
        import httpx

        response.raise_for_status.side_effect = httpx.HTTPStatusError("err", request=mock.Mock(), response=response)
    else:
        response.raise_for_status.return_value = None
    return response


def test_metric_exact_name_match(runner):
    with mock.patch.object(prom.httpx, "get", return_value=_scrape()) as get:
        result = runner.invoke(
            prom.prometheus,
            obj={"output_format": "json"},
            args=["metric", "--name", "v9_would_reject_total"],
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["matched"] == 2
    names = {s["name"] for s in data["samples"]}
    assert names == {"v9_would_reject_total"}  # no _bucket/_sum/_count leak
    get.assert_called_once()
    assert get.call_args[0][0] == "http://127.0.0.1:9009/metrics"


def test_metric_integer_counters_stay_integers(runner):
    with mock.patch.object(prom.httpx, "get", return_value=_scrape()):
        result = runner.invoke(
            prom.prometheus,
            obj={"output_format": "json"},
            args=["metric", "--name", "v9_would_reject_total"],
        )
    data = json.loads(result.output)
    values = {s["labels"]["reason"]: s["value"] for s in data["samples"]}
    assert values == {"not_at_parent": 2, "bad_sig": 0}  # ints, not 2.0


def test_metric_label_filter(runner):
    with mock.patch.object(prom.httpx, "get", return_value=_scrape()):
        result = runner.invoke(
            prom.prometheus,
            obj={"output_format": "json"},
            args=["metric", "--name", "v9_would_reject_total", "--label", "reason=not_at_parent"],
        )
    data = json.loads(result.output)
    assert data["matched"] == 1
    assert data["samples"][0]["labels"]["reason"] == "not_at_parent"


def test_metric_missing_metric_is_empty_result(runner):
    with mock.patch.object(prom.httpx, "get", return_value=_scrape()):
        result = runner.invoke(
            prom.prometheus,
            obj={"output_format": "json"},
            args=["metric", "--name", "nosuch_counter_total"],
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["matched"] == 0
    assert data["samples"] == []


def test_metric_malformed_lines_counted(runner):
    with mock.patch.object(prom.httpx, "get", return_value=_scrape()):
        result = runner.invoke(
            prom.prometheus,
            obj={"output_format": "json"},
            args=["metric", "--name", "python_info"],
        )
    data = json.loads(result.output)
    assert data["malformed_lines"] == 1
    assert data["matched"] == 1


def test_metric_non_loopback_url_refused(runner):
    with mock.patch.object(prom.httpx, "get", return_value=_scrape()) as get:
        result = runner.invoke(
            prom.prometheus,
            obj={"output_format": "json"},
            args=["metric", "--name", "x", "--url", "http://10.1.223.93:9009/metrics"],
        )
    assert result.exit_code != 0
    assert "loopback" in result.output
    get.assert_not_called()


def test_metric_non_loopback_needs_allow_remote(runner):
    with mock.patch.object(prom.httpx, "get", return_value=_scrape()) as get:
        result = runner.invoke(
            prom.prometheus,
            obj={"output_format": "json"},
            args=["metric", "--name", "v9_would_reject_total", "--url", "http://10.1.223.93:9009/metrics", "--allow-remote"],
        )
    assert result.exit_code == 0, result.output
    get.assert_called_once()


def test_metric_alternate_loopback_port(runner):
    """The bridge RPC endpoint at :8202 is a legitimate alternate source."""
    with mock.patch.object(prom.httpx, "get", return_value=_scrape("bridge_pending 3\n")):
        result = runner.invoke(
            prom.prometheus,
            obj={"output_format": "json"},
            args=["metric", "--name", "bridge_pending", "--url", "http://127.0.0.1:8202/metrics"],
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["samples"][0]["value"] == 3


def test_metric_invalid_name_refused(runner):
    result = runner.invoke(
        prom.prometheus,
        obj={"output_format": "json"},
        args=["metric", "--name", "bad name;rm"],
    )
    assert result.exit_code != 0
    assert "invalid metric name" in result.output


def test_metric_unreachable_is_clean_error(runner):
    import httpx

    with mock.patch.object(prom.httpx, "get", side_effect=httpx.ConnectError("refused")):
        result = runner.invoke(
            prom.prometheus,
            obj={"output_format": "table"},
            args=["metric", "--name", "x"],
        )
    assert result.exit_code != 0
    assert "could not reach" in result.output
    assert "Traceback" not in result.output


def test_metric_help_epilog(runner):
    result = runner.invoke(prom.prometheus, args=["metric", "--help"])
    assert result.exit_code == 0
    assert "v9_would_reject_total" in result.output
