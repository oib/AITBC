"""#2967: buyer-side result retrieval — local swarm fuse + coordinator proxy fallback.

The buyer's daemon reads the result CID over the direct buyer-provider
bitswap leg; when that leg is broken the read hangs and the paid result is
undeliverable. The CLI falls back to the coordinator's party-scoped proxy
after a short fuse. These are the wiring pins: they drive the real `result`
command, so reverting the fallback call-site must kill them.
"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

pytest.importorskip("eth_account", reason="envelope signing tests need eth-account")

PAYLOAD = b'{"text": "the correct transcript"}'
RESULT_REF = "bafyResult" + "b" * 48


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.base_url = "http://coord.local"
    client.headers = {}
    with patch("aitbc_cli.commands.agent_task.AITBCHTTPClient", return_value=client):
        with patch(
            "aitbc_cli.commands.agent_task.get_config",
            return_value=MagicMock(agent_coordinator_url="http://coord.local", blockchain_rpc_url="http://rpc.local:8202"),
        ):
            yield client


def _inbox_with_result():
    return {
        "messages": [
            {
                "message_id": "m9",
                "message_type": "task_result",
                "content": (
                    '{"task_id": "t-1", "status": "success", '
                    f'"result_ref": "{RESULT_REF}", "result_hash": "{hashlib.sha256(PAYLOAD).hexdigest()}"'
                    "}"
                ),
            }
        ]
    }


def _stream_response(content: bytes):
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.iter_content.return_value = [content]
    resp.raise_for_status = MagicMock()
    return resp


def _post_cat_fails(exc):
    """requests.post substitute: cat calls raise, daemon probes succeed."""

    def fake_post(url, **kwargs):
        if "/api/v0/cat" in str(url):
            raise exc
        return _stream_response(b"")

    return fake_post


def _invoke(runner, out_file):
    from aitbc_cli.commands.agent_task import agent_task

    return runner.invoke(
        agent_task,
        ["result", "--task-id", "t-1", "--coordinator-url", "http://coord.local", "--out", str(out_file)],
        obj={"output_format": "json"},
    )


def test_swarm_failure_falls_back_to_proxy(runner, mock_client, tmp_path):
    """WIRING PIN: local cat fails -> the proxy is consulted and its bytes served."""
    mock_client.get.side_effect = lambda path, params=None, headers=None: (
        _inbox_with_result() if path == "/api/v1/agent/messages/inbox" else {}
    )
    out_file = tmp_path / "out.json"
    with patch("aitbc_cli.commands.agent_task._daemon_available", return_value=True):
        with patch("requests.post", side_effect=_post_cat_fails(TimeoutError("bitswap leg dead"))):
            with patch("requests.get", return_value=_stream_response(PAYLOAD)) as mock_get:
                result = _invoke(runner, out_file)
    assert result.exit_code == 0, result.output
    assert out_file.read_bytes() == PAYLOAD
    # the decisive wiring assertion: the fallback actually consulted the proxy
    proxy_calls = [c for c in mock_get.call_args_list if "/v1/tasks/t-1/result" in str(c)]
    assert proxy_calls, "coordinator proxy was never consulted on swarm failure"


def test_healthy_swarm_never_touches_proxy(runner, mock_client, tmp_path):
    """Control direction: a working local read must not consult the proxy."""
    mock_client.get.side_effect = lambda path, params=None, headers=None: (
        _inbox_with_result() if path == "/api/v1/agent/messages/inbox" else {}
    )
    out_file = tmp_path / "out.json"
    with patch("aitbc_cli.commands.agent_task._daemon_available", return_value=True):
        with patch("requests.post", return_value=_stream_response(PAYLOAD)):
            with patch("requests.get") as mock_get:
                result = _invoke(runner, out_file)
    assert result.exit_code == 0, result.output
    assert out_file.read_bytes() == PAYLOAD
    proxy_calls = [c for c in mock_get.call_args_list if "/v1/tasks/t-1/result" in str(c)]
    assert not proxy_calls, "proxy consulted despite a healthy local swarm read"


def test_no_local_daemon_uses_proxy_directly(runner, mock_client, tmp_path):
    mock_client.get.side_effect = lambda path, params=None, headers=None: (
        _inbox_with_result() if path == "/api/v1/agent/messages/inbox" else {}
    )
    out_file = tmp_path / "out.json"
    with patch("aitbc_cli.commands.agent_task._daemon_available", return_value=False):
        with patch("requests.get", return_value=_stream_response(PAYLOAD)):
            result = _invoke(runner, out_file)
    assert result.exit_code == 0, result.output
    assert out_file.read_bytes() == PAYLOAD


def test_both_paths_failing_aborts(runner, mock_client, tmp_path):
    mock_client.get.side_effect = lambda path, params=None, headers=None: (
        _inbox_with_result() if path == "/api/v1/agent/messages/inbox" else {}
    )
    out_file = tmp_path / "out.json"
    with patch("aitbc_cli.commands.agent_task._daemon_available", return_value=True):
        with patch("requests.post", side_effect=_post_cat_fails(TimeoutError("swarm dead"))):
            with patch("requests.get", side_effect=ConnectionError("proxy down")):
                result = _invoke(runner, out_file)
    assert result.exit_code != 0
    assert not out_file.exists()
