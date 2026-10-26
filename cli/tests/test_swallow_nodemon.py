"""node test must exit non-zero when a connectivity sub-test fails (CLI-SWALLOW-SWEEP-2, #570)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

MODULE = "aitbc_cli.commands.node.monitor"


@pytest.fixture
def runner():
    return CliRunner()


def _client_ctx(node_info):
    """Async context manager stub matching ``async with NodeClient(...) as client``."""
    client = MagicMock()
    client.get_node_info = AsyncMock(return_value=node_info)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _invoke(runner, node_info, fmt="table", node_id="node-1"):
    from aitbc_cli.commands.node import node

    config = SimpleNamespace(nodes={node_id: MagicMock()})
    with (
        patch(f"{MODULE}.load_multichain_config", return_value=config),
        patch(f"{MODULE}.NodeClient", return_value=_client_ctx(node_info)),
    ):
        return runner.invoke(
            node,
            ["test", "--node-id", node_id],
            obj={"output": fmt, "output_format": fmt},
        )


def _all_pass_info(node_id="node-1"):
    return {"node_id": node_id, "status": "online", "version": "1.2.3"}


def test_failed_subtest_exits_nonzero(runner):
    """A FAIL row must not exit 0 (old code printed a warning and returned)."""
    info = _all_pass_info()
    info["version"] = ""  # forces the Version sub-test to FAIL
    result = _invoke(runner, info)
    assert result.exit_code != 0
    assert "FAIL" in result.output


def test_all_pass_exits_zero(runner):
    """Pin the success direction: all sub-tests PASS must still exit 0."""
    result = _invoke(runner, _all_pass_info())
    assert result.exit_code == 0
    assert "All tests passed" in result.output


def test_failed_subtest_json_error_doc(runner):
    """JSON mode: failure emits one parseable error document and exits non-zero."""
    info = _all_pass_info()
    info["version"] = ""
    result = _invoke(runner, info, fmt="json")
    assert result.exit_code != 0
    # Output contains the results document followed by the error document;
    # decode every JSON document and require exactly one error payload.
    decoder = json.JSONDecoder()
    docs, idx = [], 0
    text = result.output
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        doc, idx = decoder.raw_decode(text, idx)
        docs.append(doc)
    error_docs = [d for d in docs if isinstance(d, dict) and "error" in d]
    assert len(error_docs) == 1, result.output
    assert error_docs[0]["exit_code"] != 0


def test_node_not_found_aborts(runner):
    """Refusal for an unknown node id stays non-zero (click.Abort path)."""
    from aitbc_cli.commands.node import node

    config = SimpleNamespace(nodes={})
    with patch(f"{MODULE}.load_multichain_config", return_value=config):
        result = runner.invoke(node, ["test", "--node-id", "ghost"], obj={"output": "table", "output_format": "table"})
    assert result.exit_code != 0
    assert "not found" in result.output
