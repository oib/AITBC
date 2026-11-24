"""#2868: sign_and_submit_transaction must classify provably-local
pre-broadcast failures as definite — not leave them unflagged so the
route wedges the idempotency row as 'uncertain' for manual resolution.

Post-submit failures (the tx may have landed) stay ambiguous.
"""

import sqlite3

import pytest

from wallet_app.keystore.persistent_service import PersistentKeystoreService

from .conftest import TEST_PASSWORD


@pytest.fixture(autouse=True)
def _chain(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "test-chain")


def _svc(keystore: PersistentKeystoreService, monkeypatch) -> PersistentKeystoreService:
    keystore.create_wallet("w2868", TEST_PASSWORD)
    monkeypatch.setattr(PersistentKeystoreService, "_get_account_nonce", lambda self, addr: 0)
    return keystore


def test_bad_recipient_is_definite_not_uncertain(keystore, monkeypatch):
    """Local input validation fails before broadcast — nothing was sent,
    so the failure is definite and the idempotency row may retry."""
    svc = _svc(keystore, monkeypatch)
    result = svc.sign_and_submit_transaction("w2868", TEST_PASSWORD, "not-an-address!!", 5, nonce=0, chain_id="test-chain")
    assert result["success"] is False
    assert result.get("definite") is True
    assert "ambiguous" not in result


def test_legacy_key_scheme_is_definite(keystore, monkeypatch):
    """A wallet that cannot produce a node-verifiable signature fails
    locally — definite, not uncertain."""
    svc = _svc(keystore, monkeypatch)
    # Force the legacy-key refusal: metadata without key_scheme=secp256k1.
    import sqlite3 as _sq

    conn = _sq.connect(svc.db_path)
    conn.execute("UPDATE wallets SET metadata = ? WHERE wallet_id = ?", ('{"key_scheme": "ed25519"}', "w2868"))
    conn.commit()
    conn.close()
    result = svc.sign_and_submit_transaction("w2868", TEST_PASSWORD, "0x" + "44" * 20, 5, nonce=0, chain_id="test-chain")
    assert result["success"] is False
    assert result.get("definite") is True
    assert "ambiguous" not in result


def test_post_submit_failure_stays_ambiguous(keystore, monkeypatch):
    """A failure AFTER _submit_transaction_to_chain returned may have
    broadcast — it must NOT be marked definite."""
    svc = _svc(keystore, monkeypatch)
    monkeypatch.setattr(
        PersistentKeystoreService,
        "_submit_transaction_to_chain",
        lambda self, tx_data, sig: {"success": True, "transaction_hash": "0xabc"},
    )

    def flaky_log(self, wallet_id, action, success, ip_address=None, **kwargs):
        # Raise only on the post-submit success log — earlier access logs
        # (get_wallet/unlock) must pass so the failure lands after broadcast.
        if action == "transaction_submitted":
            raise sqlite3.OperationalError("disk full")
        return None

    monkeypatch.setattr(PersistentKeystoreService, "_log_access", flaky_log)
    result = svc.sign_and_submit_transaction("w2868", TEST_PASSWORD, "0x" + "44" * 20, 5, nonce=0, chain_id="test-chain")
    assert result["success"] is False
    assert result.get("ambiguous") is True
    assert "definite" not in result
