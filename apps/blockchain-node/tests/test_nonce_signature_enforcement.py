"""Consensus nonce/signature enforcement (v7+ strict apply).

Before this change every apply path overwrote ``tx_data["nonce"]`` with the
live account nonce before validation, so the ``tx_nonce == account.nonce``
check was a tautology everywhere and the parallel paths additionally skipped
signature verification entirely. Now:

- ``use_account_nonce_override`` limits the rewrite to v<7 replay and
  unsigned internal txs;
- ``compute_state_delta`` verifies ``signature`` when present, mirroring
  ``apply_transaction``;
- signed txs at v7+ keep their envelope nonce, so the nonce check is real.
"""

from aitbc_chain.models import Account
from aitbc_chain.state.pure_state_transition import compute_state_delta
from aitbc_chain.state.state_transition import use_account_nonce_override


def _keyed_account(balance: int = 10**9, nonce: int = 0):
    from aitbc.crypto.crypto import derive_ethereum_address, generate_ethereum_private_key

    key = generate_ethereum_private_key()
    address = derive_ethereum_address(key)
    return key, Account(chain_id="test", address=address, balance=balance, nonce=nonce)


def _signed_tx(key: str, sender: Account, nonce: int, amount: int = 10, fee: int = 1) -> dict:
    from aitbc_chain.rpc.utils import sign_transaction_data

    tx = {
        "from": sender.address,
        "to": "0x" + "bb" * 20,
        "amount": amount,
        "fee": fee,
        "nonce": nonce,
        "payload": {},
        "type": "TRANSFER",
        "chain_id": "test",
    }
    tx["signature"] = sign_transaction_data(tx, key)
    return tx


class TestNonceOverrideGate:
    def test_pre_v7_always_overrides(self):
        signed = {"signature": "0xsig", "nonce": 3}
        for version in range(2, 7):
            assert use_account_nonce_override(signed, version)

    def test_v7_signed_keeps_envelope_nonce(self):
        for version in (7, 8):
            assert not use_account_nonce_override({"signature": "0xsig"}, version)
            assert not use_account_nonce_override({"sig": "0xsig"}, version)

    def test_v7_unsigned_still_overrides(self):
        for version in (7, 8):
            assert use_account_nonce_override({}, version)
            assert use_account_nonce_override({"signature": ""}, version)
            assert use_account_nonce_override({"signature": None}, version)


class TestPurePathSignatureCheck:
    def test_valid_signature_applies(self):
        key, sender = _keyed_account()
        tx = _signed_tx(key, sender, nonce=0)
        delta = compute_state_delta({sender.address: sender}, tx, "test", tx_hash="tx1", block_version=8)
        assert delta.success, delta.error
        assert delta.sender_balance_change == -11
        assert delta.sender_nonce_change == 1

    def test_forged_signature_fails(self):
        key, sender = _keyed_account()
        _, other = _keyed_account()
        tx = _signed_tx(key, sender, nonce=0)
        tx["from"] = other.address  # signature no longer matches sender
        delta = compute_state_delta({other.address: other}, tx, "test", tx_hash="tx1", block_version=8)
        assert not delta.success
        assert "signature" in delta.error.lower()

    def test_wrong_nonce_signed_tx_fails_nonce_not_signature(self):
        """A stale/future signed nonce must surface as a nonce rejection —
        before, the override rewrote it and the check was dead."""
        key, sender = _keyed_account(nonce=0)
        tx = _signed_tx(key, sender, nonce=5)  # signature valid for nonce 5
        delta = compute_state_delta({sender.address: sender}, tx, "test", tx_hash="tx1", block_version=8)
        assert not delta.success
        assert "nonce" in delta.error.lower()

    def test_unsigned_tx_skips_signature_check(self):
        sender = Account(chain_id="test", address="ait1internal", balance=10**9, nonce=0)
        tx = {
            "from": "ait1internal",
            "to": "ait1recipient",
            "amount": 10,
            "fee": 1,
            "nonce": 0,
            "type": "TRANSFER",
        }
        delta = compute_state_delta({"ait1internal": sender}, tx, "test", tx_hash="tx1", block_version=8)
        assert delta.success, delta.error

    def test_sequential_nonce_progression_same_sender(self):
        """Two signed txs from one sender (nonces n, n+1) validate in order —
        the second sees the account nonce advanced by the first."""
        key, sender = _keyed_account(nonce=3)
        account_map = {sender.address: sender}
        tx1 = _signed_tx(key, sender, nonce=3)
        tx2 = _signed_tx(key, sender, nonce=4)
        d1 = compute_state_delta(account_map, tx1, "test", tx_hash="t1", block_version=8)
        assert d1.success, d1.error
        sender.nonce += d1.sender_nonce_change
        sender.balance += d1.sender_balance_change
        d2 = compute_state_delta(account_map, tx2, "test", tx_hash="t2", block_version=8)
        assert d2.success, d2.error
