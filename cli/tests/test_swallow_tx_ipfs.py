"""transactions/ipfs commands must abort non-zero on refusals (CLI-SWALLOW-SWEEP-2, #570).

Covers the ``_send_transaction_impl`` returns-None convention (error printed →
bare ``return None`` → exit 0), the batch "x/y successful" exit-0-on-failure
defect, the ``search`` unexpected-response-shape refusal, and the ipfs
``island swarm-key`` requests.RequestException swallow.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from click.testing import CliRunner

from aitbc_cli.commands import ipfs as ipfs_mod
from aitbc_cli.commands import transactions as tx_mod


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def _offline_send(monkeypatch, tmp_path):
    """Neutralise password/rpc resolution and point the wallet dir at scratch space."""
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
    monkeypatch.setattr(tx_mod, "resolve_wallet_password", lambda *a, **kw: "")
    monkeypatch.setattr(tx_mod, "_resolve_transaction_rpc_url", lambda *a, **kw: "http://node.test:8202")
    return tmp_path


def _write_wallet(tmp_path, name: str, data: dict[str, Any]) -> None:
    (tmp_path / f"{name}.json").write_text(json.dumps(data))


def _json_doc_count(text: str) -> int:
    """Count parseable top-level JSON documents in combined output."""
    docs = 0
    for chunk in text.split("}\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            json.loads(chunk if chunk.endswith("}") else chunk + "}")
            docs += 1
        except ValueError:
            pass
    return docs


# --- send: amount validation ------------------------------------------------


def test_send_zero_amount_aborts(runner, _offline_send):
    """amount=0 on a value type printed 'Amount must be positive' and exited 0."""
    result = runner.invoke(
        tx_mod.transactions,
        ["send", "--from", "w1", "--to", "0x52908400098527886E0F7030069857D2E4169EE7", "--amount", "0", "--password", "x"],
        obj={"output_format": "table"},
    )
    assert result.exit_code != 0
    assert "Amount must be positive" in result.output


def test_send_zero_value_type_nonzero_amount_aborts(runner, _offline_send):
    """MESSAGE with --amount 5 printed the zero-value refusal and exited 0."""
    result = runner.invoke(
        tx_mod.transactions,
        [
            "send",
            "--from",
            "w1",
            "--to",
            "0x52908400098527886E0F7030069857D2E4169EE7",
            "--amount",
            "5",
            "--type",
            "MESSAGE",
            "--password",
            "x",
        ],
        obj={"output_format": "table"},
    )
    assert result.exit_code != 0
    assert "must have amount=0" in result.output


# --- send: wallet resolution ------------------------------------------------


def test_send_missing_wallet_aborts(runner, _offline_send):
    """A wallet name with no file printed 'not found' and exited 0."""
    result = runner.invoke(
        tx_mod.transactions,
        ["send", "--from", "ghost", "--to", "0x52908400098527886E0F7030069857D2E4169EE7", "--amount", "1", "--password", "x"],
        obj={"output_format": "table"},
    )
    assert result.exit_code != 0
    assert "not found" in result.output


def test_send_wallet_without_private_key_aborts(runner, _offline_send, tmp_path):
    """An unencrypted wallet file lacking private_key exited 0 after an error line."""
    _write_wallet(tmp_path, "nopriv", {"address": "0xde709f2102306220921060314715629080e2fb77"})
    result = runner.invoke(
        tx_mod.transactions,
        ["send", "--from", "nopriv", "--to", "0x52908400098527886E0F7030069857D2E4169EE7", "--amount", "1", "--password", "x"],
        obj={"output_format": "table"},
    )
    assert result.exit_code != 0
    assert "does not contain private key" in result.output


# --- send: payload parsing --------------------------------------------------


def test_send_non_object_payload_aborts_table(runner, _offline_send):
    """--payload '[1, 2]' printed 'Payload must be a JSON object' and exited 0."""
    result = runner.invoke(
        tx_mod.transactions,
        [
            "send",
            "--from",
            "w1",
            "--to",
            "0x52908400098527886E0F7030069857D2E4169EE7",
            "--amount",
            "1",
            "--payload",
            "[1, 2]",
            "--password",
            "x",
        ],
        obj={"output_format": "table"},
    )
    assert result.exit_code != 0
    assert "Payload must be a JSON object" in result.output


def test_send_non_object_payload_json_single_doc(runner, _offline_send):
    """Under --output json the refusal must be exactly one error document."""
    result = runner.invoke(
        tx_mod.transactions,
        [
            "send",
            "--from",
            "w1",
            "--to",
            "0x52908400098527886E0F7030069857D2E4169EE7",
            "--amount",
            "1",
            "--payload",
            "[1, 2]",
            "--password",
            "x",
        ],
        obj={"output_format": "json"},
    )
    assert result.exit_code != 0
    doc = json.loads(result.stdout)
    assert doc.get("error") or doc.get("message"), result.stdout
    assert "Payload must be a JSON object" in doc["message"]


# --- batch: partial failure -------------------------------------------------


def _batch_file(tmp_path, entries):
    p = tmp_path / "batch.json"
    p.write_text(json.dumps(entries))
    return str(p)


def test_batch_partial_failure_exits_nonzero(runner, _offline_send, tmp_path):
    """One failed entry still printed the summary but the command exited 0."""
    entries = [
        {"from_wallet": "w1", "to_address": "0x52908400098527886E0F7030069857D2E4169EE7", "amount": 1},
        {"from_wallet": "w1", "to_address": "0xde709f2102306220921060314715629080e2fb77", "amount": 2},
    ]
    path = _batch_file(tmp_path, entries)
    hashes = iter(["0xhash1", None])
    with patch.object(tx_mod, "_send_transaction_impl", side_effect=lambda *a, **kw: next(hashes)):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", path, "--password", "x"],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "Batch completed: 1/2 successful" in result.output


def test_batch_partial_failure_json_single_doc(runner, _offline_send, tmp_path):
    """JSON mode: summary goes to stderr; stdout carries exactly one error doc."""
    entries = [
        {"from_wallet": "w1", "to_address": "0x52908400098527886E0F7030069857D2E4169EE7", "amount": 1},
        {"from_wallet": "w1", "to_address": "0xde709f2102306220921060314715629080e2fb77", "amount": 2},
    ]
    path = _batch_file(tmp_path, entries)
    hashes = iter(["0xhash1", None])
    with patch.object(tx_mod, "_send_transaction_impl", side_effect=lambda *a, **kw: next(hashes)):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", path, "--password", "x"],
            obj={"output_format": "json"},
        )
    assert result.exit_code != 0
    doc = json.loads(result.stdout)
    assert "Batch incomplete" in doc["message"]
    assert "Batch completed: 1/2" in result.stderr


def test_batch_all_success_still_rc0(runner, _offline_send, tmp_path):
    entries = [{"from_wallet": "w1", "to_address": "0x52908400098527886E0F7030069857D2E4169EE7", "amount": 1}]
    path = _batch_file(tmp_path, entries)
    with patch.object(tx_mod, "_send_transaction_impl", return_value="0xhash1"):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", path, "--password", "x"],
            obj={"output_format": "table"},
        )
    assert result.exit_code == 0
    assert "Batch completed: 1/1 successful" in result.output


# --- search: unexpected response shape --------------------------------------


def test_search_unexpected_shape_aborts(runner, _offline_send):
    """A non-array /rpc/transactions response printed an error and exited 0."""
    client = MagicMock()
    client.get_json.return_value = {"transactions": []}  # wrong shape: dict, not list
    with patch.object(tx_mod, "AITBCHTTPClient", return_value=client):
        result = runner.invoke(
            tx_mod.transactions,
            ["search", "--address", "0x52908400098527886E0F7030069857D2E4169EE7"],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "Unexpected response shape" in result.output


def test_search_empty_list_still_rc0(runner, _offline_send):
    """A genuinely empty result set is a read path success — stays rc 0."""
    client = MagicMock()
    client.get_json.return_value = []
    with patch.object(tx_mod, "AITBCHTTPClient", return_value=client):
        result = runner.invoke(
            tx_mod.transactions,
            ["search", "--address", "0x52908400098527886E0F7030069857D2E4169EE7"],
            obj={"output_format": "table"},
        )
    assert result.exit_code == 0
    assert "Found 0 transactions" in result.output


# --- ipfs island swarm-key --------------------------------------------------


def _invoke_swarm_key(runner, fmt="table"):
    wallet_key = MagicMock()
    wallet_key.to_hex.return_value = "ab" * 32
    with (
        patch.object(ipfs_mod, "resolve_wallet_password", return_value=""),
        patch.object(ipfs_mod, "_load_wallet_key", return_value=("0x52908400098527886E0F7030069857D2E4169EE7", wallet_key)),
        patch.object(ipfs_mod, "sign_transaction_hash", return_value="0xsig"),
        patch.object(ipfs_mod.requests, "post", side_effect=requests.ConnectionError("conn refused")),
    ):
        return runner.invoke(
            ipfs_mod.island,
            [
                "swarm-key",
                "--wallet",
                "w1",
                "--island-id",
                "island-1",
                "--chain-id",
                "test-chain",
                "--coordinator-url",
                "http://coord.test:8000",
                "--api-key",
                "k",
            ],
            obj={"output_format": fmt},
        )


def test_swarm_key_request_failure_aborts_table(runner):
    """requests.RequestException printed 'Failed to request swarm key' and exited 0."""
    result = _invoke_swarm_key(runner)
    assert result.exit_code != 0
    assert "Failed to request swarm key" in result.output


def test_swarm_key_request_failure_json_single_doc(runner):
    result = _invoke_swarm_key(runner, fmt="json")
    assert result.exit_code != 0
    doc = json.loads(result.stdout)
    assert "Failed to request swarm key" in doc["message"]
