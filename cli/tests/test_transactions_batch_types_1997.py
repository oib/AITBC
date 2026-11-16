"""#1997: `transactions send`/`batch` can queue typed nonces.

`send` gains ``--nonce-offset`` so a second pending tx from the same wallet
can be queued while the first sits in the mempool, and batch entries accept
optional ``type``/``payload`` keys so typed transactions can ride the batch
nonce-offset machinery instead of being TRANSFER-only.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import aitbc_cli.utils.chain_id as chain_id_mod
from aitbc_cli.commands import transactions as tx_mod
from aitbc_cli.utils.error_handling import CLIError

RECIPIENT = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"


@pytest.fixture
def runner():
    return CliRunner()


def _write_named_wallet(directory: Path, name: str, address: str) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps({"address": address, "private_key": "0x" + "11" * 32, "encrypted": False})
    )


def _serving_chain_lookup(chain_id):
    def _fake(rpc_url, override=None, timeout=5, *, strict=False):
        return override or chain_id

    return _fake


def test_send_nonce_offset_reaches_signed_nonce(runner, tmp_path, monkeypatch):
    """--nonce-offset N signs with account nonce + N — the queue-a-second-nonce path."""
    wallet_dir = tmp_path / "wallets"
    wallet_dir.mkdir()
    _write_named_wallet(wallet_dir, "w1", "0x1111111111111111111111111111111111111111")

    posted = []

    class _C:
        def __init__(self, base_url="", **kw):
            self.base_url = base_url

        def get(self, endpoint, **kw):
            return {"nonce": 1}

        def post(self, endpoint, json=None, **kw):
            posted.append(json)
            return {"transaction_hash": f"0xhash{len(posted)}"}

    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-test")),
        patch("aitbc_cli.commands.transactions.AITBCHTTPClient", _C),
        patch.dict("os.environ", {"AITBC_WALLET_DIR": str(wallet_dir)}),
    ):
        for extra, _expected_nonce in (([], 1), (["--nonce-offset", "1"], 2)):
            result = runner.invoke(
                tx_mod.transactions,
                [
                    "send",
                    "--from",
                    "w1",
                    "--to",
                    RECIPIENT,
                    "--amount",
                    "0.001",
                    "--password",
                    "x",
                    "--rpc-url",
                    "http://node:1",
                    *extra,
                ],
                obj={},
            )
            assert result.exit_code == 0, result.output
    assert [p["nonce"] for p in posted] == [expected_nonce for _, expected_nonce in (([], 1), (["--nonce-offset", "1"], 2))]


def test_batch_entries_carry_type_and_payload(runner, tmp_path, monkeypatch):
    """Two same-slot MESSAGE entries differing only in payload both submit —
    the dedup key must not collapse typed variants, and type/payload reach
    the signed transaction."""
    wallet_dir = tmp_path / "wallets"
    wallet_dir.mkdir()
    _write_named_wallet(wallet_dir, "w1", "0x1111111111111111111111111111111111111111")

    batch_file = tmp_path / "txs.json"
    batch_file.write_text(
        json.dumps(
            [
                {
                    "from_wallet": "w1",
                    "to_address": RECIPIENT,
                    "amount": "0",
                    "type": "MESSAGE",
                    "payload": {"text": "first"},
                },
                {
                    "from_wallet": "w1",
                    "to_address": RECIPIENT,
                    "amount": "0",
                    "type": "MESSAGE",
                    "payload": {"text": "second"},
                },
                {
                    "from_wallet": "w1",
                    "to_address": RECIPIENT,
                    "amount": "0",
                    "type": "MESSAGE",
                    "payload": {"text": "first"},
                },
            ]
        )
    )

    posted = []

    class _C:
        def __init__(self, base_url="", **kw):
            self.base_url = base_url

        def get(self, endpoint, **kw):
            return {"nonce": 1}

        def post(self, endpoint, json=None, **kw):
            posted.append(json)
            return {"transaction_hash": f"0xhash{len(posted)}"}

    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-test")),
        patch("aitbc_cli.commands.transactions.AITBCHTTPClient", _C),
        patch.dict("os.environ", {"AITBC_WALLET_DIR": str(wallet_dir)}),
    ):
        result = runner.invoke(
            tx_mod.transactions,
            ["batch", "--transactions-file", str(batch_file), "--password", "x", "--rpc-url", "http://node:1"],
            obj={},
        )
    assert result.exit_code == 0, result.output
    # Third entry is an exact duplicate of the first → skipped, not resent.
    assert len(posted) == 2
    assert all(p["type"] == "MESSAGE" for p in posted)
    assert [p["payload"]["text"] for p in posted] == ["first", "second"]
    # Per-sender nonce offsets still apply across the typed entries.
    assert [p["nonce"] for p in posted] == [1, 2]


def test_process_batch_entry_rejects_non_object_payload():
    """A payload that is neither a JSON object nor a JSON string fails the entry."""
    results: list = []
    seen_entries: set = set()
    seen_hashes: set = set()
    nonce_offsets: dict = {}
    with pytest.raises(CLIError):
        tx_mod._process_batch_entry(
            {
                "from_wallet": "w1",
                "to_address": RECIPIENT,
                "amount": "1",
                "payload": ["not", "an", "object"],
            },
            "pw",
            "http://node:1",
            seen_entries,
            seen_hashes,
            nonce_offsets,
            results,
        )
