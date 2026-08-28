"""Unit tests for chain-backed escrow lock and release."""

from decimal import Decimal

from aitbc.utils import DEFAULT_TX_FEE_UNITS, ait_to_units
from aitbc.crypto.signature_recovery import canonical_address

import aitbc_chain.rpc.escrow_routes as escrow_routes


# Deterministic, valid EIP-55 0x addresses.
# Derived via eth_account.Account.from_key(sha256(name.encode()).digest()).address
BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"
NODE_WALLET = "0xADC923a0928B8415E666206D3703a870C1d578CE"

# The routes canonicalise 0x addresses to lowercase for string comparison.
BUYER_CANONICAL = canonical_address(BUYER)
PROVIDER_CANONICAL = canonical_address(PROVIDER)
NODE_WALLET_CANONICAL = canonical_address(NODE_WALLET)


def _patch_env(monkeypatch):
    monkeypatch.setattr(escrow_routes, "_NODE_WALLET", NODE_WALLET)
    monkeypatch.setattr(escrow_routes, "_CHAIN_ID", "ait-test")


class TestEscrowLockRoutes:
    """Test the escrow route helpers and request validation."""

    def test_build_lock_tx_amount_in_units(self, monkeypatch):
        _patch_env(monkeypatch)
        tx, units = escrow_routes._build_lock_tx("job1", BUYER, PROVIDER, Decimal("1.5"), 5)
        assert units == ait_to_units(Decimal("1.5"))
        assert tx["amount"] == ait_to_units(Decimal("1.5"))
        assert tx["from"] == BUYER_CANONICAL
        assert tx["to"] == NODE_WALLET_CANONICAL
        assert tx["type"] == "ESCROW_LOCK"
        assert tx["payload"]["job_id"] == "job1"
        assert tx["payload"]["provider"] == PROVIDER_CANONICAL

    def test_compute_signing_hash_excludes_signature_and_value(self, monkeypatch):
        _patch_env(monkeypatch)
        tx, _ = escrow_routes._build_lock_tx("job1", BUYER, PROVIDER, Decimal("1"), 0, fee=DEFAULT_TX_FEE_UNITS)
        tx["value"] = tx["amount"]  # normalize_transaction_data adds this
        tx["signature"] = "0x1234"
        h1 = escrow_routes._compute_tx_signing_hash(tx)
        tx2 = tx.copy()
        tx2["signature"] = "0x5678"
        h2 = escrow_routes._compute_tx_signing_hash(tx2)
        assert h1 == h2, "signature should not affect signing hash"
