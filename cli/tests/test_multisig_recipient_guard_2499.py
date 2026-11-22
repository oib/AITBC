"""#2499: the #2362 multisig-recipient refusal covers every send path.

``wallet send`` already refused funding a locally recorded ``*_multisig.json``
address (it has no spendable key — funds sent there are unrecoverable), but
``transactions send``, ``transactions batch`` and the MCP
``aitbc_transactions_send`` tool still funded it. The check now lives in
``utils.wallet_paths.multisig_recipient_refusal`` and runs inside
``_send_transaction_impl`` — the single funnel for all of them.
"""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import transactions as tx_cmd
from aitbc_cli.utils.error_handling import CLIError
from aitbc_cli.utils.address import to_eip55
from aitbc_cli.utils.wallet_loader import write_json_0600
from aitbc_cli.utils.wallet_paths import multisig_recipient_refusal

MULTISIG_ADDR = to_eip55("0x" + "ab" * 20)


def _make_multisig(wallet_dir: Path, name: str = "team") -> None:
    wallet_dir.mkdir(parents=True, exist_ok=True)
    write_json_0600(
        wallet_dir / f"{name}_multisig.json",
        {
            "wallet_id": name,
            "type": "multisig",
            "address": MULTISIG_ADDR,
            "signers": ["0x" + "aa" * 20],
            "threshold": 1,
        },
    )


def test_shared_guard_finds_multisig_in_any_search_dir(tmp_path, monkeypatch):
    """The guard scans every wallet search dir, not just the configured one."""
    _make_multisig(tmp_path / "wallets")
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "wallets"))
    from aitbc_cli.utils.wallet_paths import wallet_search_dirs

    assert multisig_recipient_refusal(MULTISIG_ADDR.upper().replace("0X", "0x"), wallet_search_dirs())
    assert multisig_recipient_refusal(to_eip55("0x" + "00" * 20), wallet_search_dirs()) is None


def test_send_transaction_impl_refuses_multisig_recipient(tmp_path, monkeypatch):
    """``transactions send`` — and therefore batch + MCP send — refuses before signing."""
    _make_multisig(tmp_path / "wallets")
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path / "wallets"))
    with pytest.raises(CLIError, match="unrecoverable"):
        tx_cmd._send_transaction_impl(
            "no-such-wallet",
            MULTISIG_ADDR,
            Decimal("1"),
            Decimal("0.001"),
            "pw",
            keystore_dir=tmp_path,
        )


def test_batch_refuses_multisig_recipient_before_any_submit(tmp_path, monkeypatch):
    """A batch entry naming the multisig address aborts the run; nothing is submitted."""
    wallet_dir = tmp_path / "wallets"
    wallet_dir.mkdir()
    (wallet_dir / "w1.json").write_text(
        json.dumps({"address": "0x" + "11" * 20, "private_key": "0x" + "44" * 32, "encrypted": False})
    )
    _make_multisig(wallet_dir)

    batch_file = tmp_path / "txs.json"
    batch_file.write_text(
        json.dumps(
            [
                {"from_wallet": "w1", "to_address": MULTISIG_ADDR, "amount": "1"},
                {"from_wallet": "w1", "to_address": "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B", "amount": "1"},
            ]
        )
    )

    posts: list[str] = []

    class _C:
        def __init__(self, base_url="", **kw):
            self.base_url = base_url

        def get(self, endpoint, **kw):
            return {"nonce": 1}

        def post(self, endpoint, json=None, **kw):
            posts.append(endpoint)
            return {"transaction_hash": "0xhash"}

    monkeypatch.setenv("AITBC_WALLET_DIR", str(wallet_dir))
    monkeypatch.delenv("CHAIN_ID", raising=False)
    import aitbc_cli.utils.chain_id as chain_id_mod

    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=lambda rpc_url, override=None, **kw: override or "ait-test"),
        patch("aitbc_cli.commands.transactions.AITBCHTTPClient", _C),
    ):
        result = CliRunner().invoke(
            tx_cmd.transactions,
            ["batch", "--transactions-file", str(batch_file), "--password", "x", "--rpc-url", "http://node:1"],
            obj={},
        )
    assert result.exit_code != 0
    assert "unrecoverable" in result.output
    assert posts == []
