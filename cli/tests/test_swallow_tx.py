"""transactions batch: skipped duplicate entries must not fail the batch (#570 follow-up).

A duplicate batch entry is a designed skip (``_process_batch_entry`` marks the
row ``skipped=True`` and continues), not a send failure — a retry script
resubmitting an already-processed file must still get rc 0 when every
non-duplicate row succeeded. Real send failures still abort non-zero.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

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


def _batch_file(tmp_path, entries: list[dict[str, Any]]) -> str:
    p = tmp_path / "batch.json"
    p.write_text(json.dumps(entries))
    return str(p)


ENTRY1 = {"from_wallet": "w1", "to_address": "0x52908400098527886E0F7030069857D2E4169EE7", "amount": 1}
ENTRY2 = {"from_wallet": "w1", "to_address": "0xde709f2102306220921060314715629080e2fb77", "amount": 2}


def test_batch_all_success_rc0(runner, _offline_send, tmp_path):
    path = _batch_file(tmp_path, [ENTRY1, ENTRY2])
    hashes = iter(["0xhash1", "0xhash2"])
    with patch.object(tx_mod, "_send_transaction_impl", side_effect=lambda *a, **kw: next(hashes)):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", path, "--password", "x"],
            obj={"output_format": "table"},
        )
    assert result.exit_code == 0
    assert "Batch completed: 2/2 successful" in result.output


def test_batch_skipped_duplicate_still_rc0(runner, _offline_send, tmp_path):
    """A duplicate row is a designed skip: all other rows succeeding → rc 0."""
    path = _batch_file(tmp_path, [ENTRY1, ENTRY2, dict(ENTRY1)])
    hashes = iter(["0xhash1", "0xhash2"])
    with patch.object(tx_mod, "_send_transaction_impl", side_effect=lambda *a, **kw: next(hashes)):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", path, "--password", "x"],
            obj={"output_format": "table"},
        )
    assert result.exit_code == 0, result.output
    assert "Duplicate batch entry skipped" in result.output
    assert "Batch completed: 2/3 successful (1 duplicate(s) skipped)" in result.output


def test_batch_skipped_duplicate_json_rc0(runner, _offline_send, tmp_path):
    """JSON mode: a skip-only batch still exits 0."""
    path = _batch_file(tmp_path, [ENTRY1, dict(ENTRY1)])
    with patch.object(tx_mod, "_send_transaction_impl", return_value="0xhash1"):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", path, "--password", "x"],
            obj={"output_format": "json"},
        )
    assert result.exit_code == 0, result.output


def test_batch_real_failure_nonzero(runner, _offline_send, tmp_path):
    """A send returning no hash is a real failure and still aborts non-zero."""
    path = _batch_file(tmp_path, [ENTRY1, ENTRY2])
    hashes = iter(["0xhash1", None])
    with patch.object(tx_mod, "_send_transaction_impl", side_effect=lambda *a, **kw: next(hashes)):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", path, "--password", "x"],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "Batch completed: 1/2 successful" in result.output
    assert "Batch incomplete" in result.output


def test_batch_real_failure_json_single_doc(runner, _offline_send, tmp_path):
    """JSON mode: summary goes to stderr; stdout carries exactly one error doc."""
    path = _batch_file(tmp_path, [ENTRY1, ENTRY2])
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


def test_batch_skip_plus_real_failure_nonzero(runner, _offline_send, tmp_path):
    """A skipped duplicate does not mask a real failure — batch still aborts."""
    path = _batch_file(tmp_path, [ENTRY1, ENTRY2, dict(ENTRY1)])
    hashes = iter(["0xhash1", None])
    with patch.object(tx_mod, "_send_transaction_impl", side_effect=lambda *a, **kw: next(hashes)):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", path, "--password", "x"],
            obj={"output_format": "table"},
        )
    assert result.exit_code != 0
    assert "Batch completed: 1/3 successful (1 duplicate(s) skipped)" in result.output
    assert "Batch incomplete" in result.output
