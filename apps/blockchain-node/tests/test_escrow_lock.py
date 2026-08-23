"""Unit tests for chain-backed escrow lock and release."""

from decimal import Decimal


import aitbc_chain.rpc.escrow_routes as escrow_routes


def _patch_env(monkeypatch):
    monkeypatch.setattr(escrow_routes, "_NODE_WALLET", "ait1node000000000000000000000000000000000000")
    monkeypatch.setattr(escrow_routes, "_CHAIN_ID", "ait-test")


class TestEscrowLockRoutes:
    """Test the escrow route helpers and request validation."""

    def test_build_lock_tx_amount_in_seconds(self, monkeypatch):
        _patch_env(monkeypatch)
        tx, seconds = escrow_routes._build_lock_tx("job1", "ait1buyer", "ait1provider", Decimal("1.5"), 5)
        assert seconds == 5400
        assert tx["amount"] == 5400
        assert tx["from"] == "ait1buyer"
        assert tx["to"] == "ait1node000000000000000000000000000000000000"
        assert tx["type"] == "ESCROW_LOCK"
        assert tx["payload"]["job_id"] == "job1"
        assert tx["payload"]["provider"] == "ait1provider"

    def test_compute_signing_hash_excludes_signature_and_value(self, monkeypatch):
        _patch_env(monkeypatch)
        tx, _ = escrow_routes._build_lock_tx("job1", "ait1buyer", "ait1provider", Decimal("1"), 0, fee=36)
        tx["value"] = tx["amount"]  # normalize_transaction_data adds this
        tx["signature"] = "0x1234"
        h1 = escrow_routes._compute_tx_signing_hash(tx)
        tx2 = tx.copy()
        tx2["signature"] = "0x5678"
        h2 = escrow_routes._compute_tx_signing_hash(tx2)
        assert h1 == h2, "signature should not affect signing hash"
