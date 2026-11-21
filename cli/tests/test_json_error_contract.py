"""CLI-JSON-ERRORS-CONSISTENT-1 (#2438): refusal paths must emit exactly one
JSON document on stdout under ``--output json`` — never plain stderr text,
never two JSON objects, never text-then-JSON.

These tests drive real command callbacks into their refusal branches and
parse stdout as a single JSON document. stderr is kept separate
(``mix_stderr=False``) so status-line noise cannot masquerade as payload.
"""

import json

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.trade as trade_mod
from aitbc.exceptions import NetworkError
from aitbc_cli.commands.bridge._group import bridge
from aitbc_cli.commands.bridge import _ledger  # noqa: F401 - registers deposits
from aitbc_cli.commands.exchange_island import exchange_island
from aitbc_cli.commands.market._group import market
from aitbc_cli.commands.market import jobs as market_jobs  # noqa: F401 - registers run
from aitbc_cli.commands.trade import trade
from aitbc_cli.commands.transactions import transactions


@pytest.fixture
def runner():
    return CliRunner()


def _assert_json_refusal(result, exit_code=None):
    assert result.exit_code != 0
    # Invoking the group directly surfaces the CLIError as result.exception;
    # the payload's exit_code must match the error's declared code.
    from aitbc_cli.utils.error_handling import CLIError

    assert isinstance(result.exception, CLIError)
    if exit_code is not None:
        assert result.exception.exit_code == exit_code
    # stdout must be exactly one parseable JSON document.
    payload = json.loads(result.stdout)
    assert payload["error"]
    assert payload["message"]
    assert payload["exit_code"] == result.exception.exit_code
    return payload


def test_transactions_send_invalid_keyenv_name_is_json(runner):
    result = runner.invoke(
        transactions,
        ["send", "--key-env", "1NOT_A_NAME!", "--to", "0x" + "11" * 20, "--amount", "1"],
        obj={"output_format": "json"},
    )
    payload = _assert_json_refusal(result)
    assert "key-env" in payload["message"]


def test_transactions_send_requires_sender_or_keyenv_is_json(runner):
    result = runner.invoke(
        transactions,
        ["send", "--to", "0x" + "11" * 20, "--amount", "1"],
        obj={"output_format": "json"},
    )
    _assert_json_refusal(result)


def test_trade_network_refusal_is_json(runner, monkeypatch):
    class _Down:
        def get_json(self, *a, **kw):
            raise NetworkError("connection refused")

        def get(self, *a, **kw):
            raise NetworkError("connection refused")

        def post(self, *a, **kw):
            raise NetworkError("connection refused")

        def close(self):
            pass

    monkeypatch.setattr(trade_mod, "_get_client", lambda *a, **kw: _Down())
    result = runner.invoke(trade, ["chains"], obj={"output_format": "json"})
    payload = _assert_json_refusal(result, exit_code=2)
    assert "Network error" in payload["message"]


def test_trade_group_api_key_flag_still_parses(runner, monkeypatch):
    """The group --api-key must not break JSON refusals (#2437 + #2438)."""

    class _Down:
        def get_json(self, *a, **kw):
            raise NetworkError("connection refused")

        def close(self):
            pass

    monkeypatch.setattr(trade_mod, "_get_client", lambda *a, **kw: _Down())
    result = runner.invoke(trade, ["--api-key", "k", "chains"], obj={"output_format": "json"})
    _assert_json_refusal(result, exit_code=2)


def test_exchange_island_buy_rejects_nonpositive_amount_as_json(runner):
    result = runner.invoke(
        exchange_island,
        ["buy", "--ait-amount", "-1", "--quote-currency", "ETH"],
        obj={"output_format": "json"},
    )
    _assert_json_refusal(result)


def test_bridge_deposits_unknown_txhash_is_json_not_found(runner):
    """Real subprocess path: admin `status` exits 3 → NotFoundError → JSON, exit 2."""
    result = runner.invoke(
        bridge,
        ["deposits", "--tx-hash", "0x" + "00" * 32],
        obj={"output_format": "json"},
    )
    payload = _assert_json_refusal(result, exit_code=2)
    assert "no deposit row" in payload["message"]


def test_market_run_unsupported_service_is_json(runner, monkeypatch):
    monkeypatch.setattr(market_jobs, "_resolve_offer", lambda *a, **kw: {"service_type": "bogus-svc"})
    monkeypatch.setattr(market_jobs, "get_market_wallet", lambda *a, **kw: ("0x" + "11" * 20, "key", "w"))
    result = runner.invoke(
        market,
        ["run", "--offer-id-or-plugin-id", "offer-x", "--prompt", "hi"],
        obj={"output_format": "json"},
    )
    _assert_json_refusal(result)


def test_not_found_keyword_maps_to_exit_2():
    """Auto-categorisation: 'not found' refusals exit 2, not validation's 4."""
    import click

    from aitbc_cli.utils.error_handling import abort

    runner = CliRunner()

    @click.command()
    @click.pass_context
    def probe(ctx):
        abort(ctx, "offer tx_9 not found")

    result = runner.invoke(probe, [], obj={"output_format": "json"})
    from aitbc_cli.utils.error_handling import NotFoundError

    assert isinstance(result.exception, NotFoundError)
    assert result.exception.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"] == "NotFoundError"
    assert payload["exit_code"] == 2
