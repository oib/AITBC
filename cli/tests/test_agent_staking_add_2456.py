"""#2456 AGENT-STAKING-ADD-ECHO-1 pins — CLI half.

- ``agent-staking status`` tags each matched transfer ``kind`` so a
  top-up (STAKE_LOCK carrying ``additional_amount``) reads differently
  from the original lock.
- ``post_signed``/``get_json`` map a 4xx policy refusal to
  ValidationError (exit 4) with the node's ``detail`` — an early
  ``unbond`` 400 must not surface as NetworkError (exit 2); the
  ``locked_until`` timestamp rides as a structured JSON field.
"""

import json

import click
import requests
from click.testing import CliRunner

from aitbc_cli.commands import agent_staking as agent_staking_mod
from aitbc_cli.utils import signed_rpc
from aitbc_cli.utils.error_handling import ValidationError
from aitbc.exceptions import NetworkError


class _Client:
    def __init__(self, base_url=None, timeout=None):
        pass

    def get_json(self, path, params=None):
        tx_type = (params or {}).get("transaction_type")
        if tx_type == "STAKE_LOCK":
            return [
                {
                    "tx_hash": "0x" + "01" * 32,
                    "type": tx_type,
                    "payload": {"agent_stake_id": "s1", "lock_days": 30},
                },
                {
                    "tx_hash": "0x" + "02" * 32,
                    "type": tx_type,
                    "payload": {"agent_stake_id": "s1", "lock_days": 30, "additional_amount": 18_000_000},
                },
            ]
        return []


def test_status_marks_lock_vs_topup(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(agent_staking_mod, "AITBCHTTPClient", _Client)
    result = runner.invoke(
        agent_staking_mod.agent_staking,
        obj={"output_format": "json"},
        args=["status", "--stake-id", "s1", "--json"],
    )
    assert result.exit_code == 0, result.output
    locks = json.loads(result.output)["transactions"]["STAKE_LOCK"]
    assert [tx["kind"] for tx in locks] == ["lock", "topup"]


def _http_400(detail: str) -> NetworkError:
    """A NetworkError wrapping a requests.HTTPError the way
    AITBCHTTPClient raises it (``raise NetworkError(...) from http_err``)."""
    req = requests.Request("POST", "http://node:8202/rpc/agent-staking/stake/s1/unbond").prepare()
    resp = requests.Response()
    resp.status_code = 400
    resp.url = str(req.url)
    resp._content = json.dumps({"detail": detail}).encode()
    resp.headers["Content-Type"] = "application/json"
    http_err = requests.HTTPError("400 Client Error", response=resp)
    net_err = NetworkError(f"POST request failed: 400 Client Error: {detail}")
    net_err.__cause__ = http_err
    return net_err


def _invoke_abort(exc):
    @click.command()
    @click.pass_context
    def cmd(ctx):
        signed_rpc._abort_request_error(ctx, "/rpc/agent-staking/stake/s1/unbond", exc)

    return CliRunner().invoke(cmd, obj={"output_format": "json"})


def test_early_unbond_400_is_validation_error_with_locked_until():
    detail = "Lock period not expired. Locked until: 2026-11-22T20:53:59+00:00"
    result = _invoke_abort(_http_400(detail))
    assert isinstance(result.exception, ValidationError)
    assert result.exception.exit_code == 4
    payload = json.loads(result.output)
    assert payload["exit_code"] == 4
    assert payload["locked_until"] == "2026-11-22T20:53:59+00:00"
    assert "Lock period not expired" in payload["message"]


def test_4xx_without_locked_until_still_validation_error():
    result = _invoke_abort(_http_400("Stake is not active: unbonding"))
    assert isinstance(result.exception, ValidationError)
    payload = json.loads(result.output)
    assert payload["exit_code"] == 4
    assert "locked_until" not in payload


def test_transport_failure_keeps_network_error():
    result = _invoke_abort(NetworkError("POST request failed: connection refused"))
    # No response in the chain → auto-categorised: 'request failed' is an
    # API keyword but the exception NAME NetworkError wins → exit 2.
    assert result.exception.exit_code == 2
