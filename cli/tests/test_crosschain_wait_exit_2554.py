"""AUDIT-CROSSCHAIN-WAIT-EXIT-1 (#2554): ``crosschain swap``/``bridge``
``--wait`` must exit non-zero when the transfer failed, refunded, timed
out, or the status poll broke — only ``completed`` is success.
"""

import json
from unittest import mock

import pytest
from click.testing import CliRunner
from eth_keys import keys as eth_keys

import aitbc_cli.commands.cross_chain as cross_mod
from aitbc_cli.commands.cross_chain import bridge, swap
from aitbc_cli.utils.http_client import NetworkError

_PRIV = "0x" + "11" * 32


@pytest.fixture
def runner():
    return CliRunner()


def _addr(priv: str) -> str:
    return str(eth_keys.PrivateKey(bytes.fromhex(priv.removeprefix("0x"))).public_key.to_checksum_address())


def _wallet(tmp_path, monkeypatch):
    (tmp_path / "w.json").write_text(json.dumps({"private_key": _PRIV, "address": _addr(_PRIV)}))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))


def _client(post_result, get_side_effect):
    client = mock.Mock()
    client.post = mock.Mock(return_value=post_result)
    responses = [get_side_effect] if isinstance(get_side_effect, Exception) else list(get_side_effect)

    def _get(url, **kwargs):
        # #2597: swap now GETs /rpc/cross-chain/rates before signing; answer
        # it with a parity rate and leave the queue for status polls.
        if "rates" in url:
            return {"rates": {"chain-a::chain-b": 1.0}}
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client.get = mock.Mock(side_effect=_get)
    return client


def _run_swap(runner, client, extra=()):
    with mock.patch.object(cross_mod, "AITBCHTTPClient", return_value=client):
        return runner.invoke(
            swap,
            obj={"output_format": "table"},
            args=[
                "--from-chain",
                "chain-a",
                "--to-chain",
                "chain-b",
                "--from-token",
                "AIT",
                "--to-token",
                "AIT",
                "--amount",
                "1",
                "--wallet",
                "w",
                "--wait",
                *extra,
            ],
        )


def _run_bridge(runner, client, extra=()):
    with mock.patch.object(cross_mod, "AITBCHTTPClient", return_value=client):
        return runner.invoke(
            bridge,
            obj={"output_format": "table"},
            args=[
                "--source-chain",
                "chain-a",
                "--target-chain",
                "chain-b",
                "--token",
                "AIT",
                "--amount",
                "1",
                "--wallet",
                "w",
                "--wait",
                *extra,
            ],
        )


def test_swap_wait_failed_exits_nonzero(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = _client({"success": True, "swap_id": "swap_x"}, [{"status": "failed"}])
    result = _run_swap(runner, client)
    assert result.exit_code != 0
    assert "without completion" in result.output
    assert "failed" in result.output


def test_swap_wait_refunded_exits_nonzero(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = _client({"success": True, "swap_id": "swap_x"}, [{"status": "refunded"}])
    result = _run_swap(runner, client)
    assert result.exit_code != 0
    assert "without completion" in result.output


def test_swap_wait_timeout_exits_nonzero(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    # Status stays non-terminal; --timeout 0 ends the poll after the first read.
    client = _client({"success": True, "swap_id": "swap_x"}, [{"status": "pending"}])
    result = _run_swap(runner, client, extra=["--timeout", "0"])
    assert result.exit_code != 0
    assert "without completion" in result.output


def test_swap_wait_poll_error_exits_nonzero(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = _client({"success": True, "swap_id": "swap_x"}, NetworkError("connection refused"))
    result = _run_swap(runner, client)
    assert result.exit_code != 0
    assert "without completion" in result.output
    assert "no response" in result.output


def test_swap_wait_completed_exits_zero(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = _client({"success": True, "swap_id": "swap_x"}, [{"status": "completed"}])
    result = _run_swap(runner, client)
    assert result.exit_code == 0, result.output


def test_bridge_wait_failed_exits_nonzero(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = _client({"success": True, "bridge_id": "b_x"}, [{"status": "failed"}])
    result = _run_bridge(runner, client)
    assert result.exit_code != 0
    assert "without completion" in result.output


def test_bridge_wait_completed_exits_zero(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = _client({"success": True, "bridge_id": "b_x"}, [{"status": "completed"}])
    result = _run_bridge(runner, client)
    assert result.exit_code == 0, result.output
