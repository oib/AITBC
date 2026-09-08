"""S-4 residual: pure_state_transition is block-version aware.

The parallel execution paths disable themselves for v3 blocks because the pure
state functions do not yet model v3 escrow rules (per-escrow addresses,
settlement authority, etc.).  This test pins the contract so the residual
"compute_state_delta takes no block_version" stays closed.
"""

from aitbc_chain.state.pure_state_transition import compute_state_delta
from aitbc_chain.models import Account


def test_compute_state_delta_accepts_block_version():
    sender = "ait1sender"
    recipient = "ait1recipient"
    account_map = {
        sender: Account(chain_id="test", address=sender, balance=1000, nonce=0),
    }
    tx = {
        "from": sender,
        "to": recipient,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=2)
    assert delta.success
    assert delta.sender_balance_change == -11
    assert delta.recipient_balance_change == 10


def test_v3_escrow_lock_rejects_parallel_path():
    sender = "ait1sender"
    recipient = "ait1recipient"
    account_map = {
        sender: Account(chain_id="test", address=sender, balance=1000, nonce=0),
    }
    tx = {
        "from": sender,
        "to": recipient,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_LOCK",
        "payload": {"job_id": "job-1", "provider": recipient},
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=3)
    assert not delta.success
    assert "v3 ESCROW_LOCK not supported by parallel state transition" in delta.error


def test_v3_escrow_release_rejects_parallel_path():
    sender = "ait1sender"
    recipient = "ait1recipient"
    account_map = {
        sender: Account(chain_id="test", address=sender, balance=1000, nonce=0),
    }
    tx = {
        "from": sender,
        "to": recipient,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "job-1"},
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=3)
    assert not delta.success
    assert "v3 ESCROW_RELEASE not supported by parallel state transition" in delta.error
