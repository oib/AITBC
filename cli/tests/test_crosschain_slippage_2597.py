"""AUDIT-CROSSCHAIN-SLIPPAGE-LIMIT-1 (#2597): ``crosschain swap
--slippage`` was signed and stored but never enforced, had no range check
despite the '(0-0.1)' help, and ``swaps --limit`` accepted negatives.

Now: --slippage is bounded to [0, 0.1], and unless --min-amount is given
the CLI derives the receive-floor from the server quote
(expected_units * (1 - slippage)) so the guard is real. --limit >= 1.
"""

import json
from unittest import mock

import pytest
from click.testing import CliRunner
from eth_keys import keys as eth_keys

import aitbc_cli.commands.cross_chain as cross_mod
from aitbc_cli.commands.cross_chain import swaps, swap
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


def _client(rates=None, post_result=None):
    client = mock.Mock()
    client.post = mock.Mock(return_value=post_result or {"success": True, "swap_id": "s1"})
    client.get = mock.Mock(return_value=rates if rates is not None else {"rates": {"chain-a::chain-b": 1.0}})
    return client


def _swap_args(extra=()):
    return [
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
        *extra,
    ]


def _run_swap(runner, client, extra=()):
    with mock.patch.object(cross_mod, "AITBCHTTPClient", return_value=client):
        return runner.invoke(swap, obj={"output_format": "table"}, args=_swap_args(extra))


@pytest.mark.parametrize("bad", ["-0.1", "0.11", "1.0"])
def test_slippage_out_of_range_rejected(runner, tmp_path, monkeypatch, bad):
    _wallet(tmp_path, monkeypatch)
    result = _run_swap(runner, _client(), ["--slippage", bad])
    assert result.exit_code == 2


def test_slippage_nan_rejected(runner, tmp_path, monkeypatch):
    # FloatRange can't see NaN (every comparison is False) — the explicit
    # finiteness check catches it before it reaches the quote math.
    _wallet(tmp_path, monkeypatch)
    result = _run_swap(runner, _client(), ["--slippage", "nan"])
    assert result.exit_code != 0
    assert "finite" in result.output


def test_slippage_derives_min_amount_from_quote(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = _client(rates={"rates": {"chain-a::chain-b": 2.0}})
    result = _run_swap(runner, client, ["--slippage", "0.1"])
    assert result.exit_code == 0, result.output
    body = client.post.call_args.kwargs["json"]
    # amount 1 AIT = 36_000_000 units; rate 2.0 -> expected 72_000_000;
    # slippage 0.1 -> floor 64_800_000.
    assert body["min_amount"] == 64_800_000
    assert body["slippage_tolerance"] == 0.1


def test_explicit_min_amount_overrides_derived(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = _client()
    result = _run_swap(runner, client, ["--min-amount", "0.5"])
    assert result.exit_code == 0, result.output
    body = client.post.call_args.kwargs["json"]
    assert body["min_amount"] == 18_000_000  # 0.5 AIT in units, not the derived floor
    # No quote lookup needed when --min-amount is explicit.
    client.get.assert_not_called()


def test_unconfigured_pair_aborts_before_signing(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = _client(rates={"rates": {}})
    args = [
        "--from-chain",
        "chain-a",
        "--to-chain",
        "chain-b",
        "--from-token",
        "AIT",
        "--to-token",
        "OTHER",
        "--amount",
        "1",
        "--wallet",
        "w",
    ]
    with mock.patch.object(cross_mod, "AITBCHTTPClient", return_value=client):
        result = runner.invoke(swap, obj={"output_format": "table"}, args=args)
    assert result.exit_code != 0
    assert "No swap rate configured" in result.output
    client.post.assert_not_called()


def test_quote_lookup_failure_aborts(runner, tmp_path, monkeypatch):
    _wallet(tmp_path, monkeypatch)
    client = mock.Mock()
    client.get = mock.Mock(side_effect=NetworkError("connection refused"))
    client.post = mock.Mock()
    result = _run_swap(runner, client)
    assert result.exit_code != 0
    assert "Quote lookup failed" in result.output
    client.post.assert_not_called()


@pytest.mark.parametrize("bad", ["0", "-5"])
def test_swaps_limit_must_be_positive(runner, bad):
    result = CliRunner().invoke(swaps, ["--limit", bad], obj={"output_format": "table"})
    assert result.exit_code == 2
