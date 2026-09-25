"""S-4: pure_state_transition is block-version aware.

The parallel execution paths disable themselves for v3 blocks containing
ESCROW_RELEASE/ESCROW_REFUND until those are modeled. ESCROW_LOCK v3 is
implemented: funds go to a deterministic per-escrow address and the provider
account is ensured.
"""

from aitbc_chain.config import settings
from aitbc_chain.state.pure_state_transition import _escrow_address, compute_state_delta
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


def test_v3_escrow_lock_creates_escrow_and_provider():
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
    assert delta.success
    assert delta.sender_balance_change == -11
    assert delta.recipient_balance_change == 10
    assert delta.recipient.startswith("0x")
    assert delta.recipient != recipient
    assert recipient in delta.extra_accounts


def test_v3_escrow_lock_rejects_missing_job_id():
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
        "payload": {"provider": recipient},
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=3)
    assert not delta.success
    assert "ESCROW_LOCK v3 payload must include job_id" in delta.error


def test_v3_escrow_lock_rejects_missing_provider():
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
        "payload": {"job_id": "job-1"},
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=3)
    assert not delta.success
    assert "ESCROW_LOCK v3 payload must include provider" in delta.error


def test_v2_escrow_lock_creates_provider():
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
        "payload": {"provider": recipient},
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=2)
    assert delta.success
    assert delta.sender_balance_change == -11
    assert delta.recipient_balance_change == 10
    assert delta.recipient == recipient
    assert recipient in delta.extra_accounts


def test_v3_escrow_release_from_escrow():
    """A v3 ESCROW_RELEASE debits the per-escrow address and credits the provider."""
    buyer = "ait1buyer"
    provider = "ait1provider"
    authority = "ait1authority"
    escrow_addr = _escrow_address("job-1")
    account_map = {
        buyer: Account(chain_id="test", address=buyer, balance=1000, nonce=0),
        authority: Account(chain_id="test", address=authority, balance=100, nonce=0),
        escrow_addr: Account(chain_id="test", address=escrow_addr, balance=10, nonce=0),
    }
    tx = {
        "from": authority,
        "to": provider,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "job-1"},
    }
    context = {
        "job-1": {
            "lock_version": 3,
            "expected_beneficiary": provider,
            "escrow_addr": escrow_addr,
        }
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=3, escrow_context=context)
    assert delta.success
    assert delta.sender_balance_change == -1
    assert delta.recipient_balance_change == 10
    assert delta.recipient == provider
    assert delta.extra_debits == {escrow_addr: -10}


def test_v3_escrow_refund_from_escrow():
    """A v3 ESCROW_REFUND debits the per-escrow address and credits the buyer."""
    buyer = "ait1buyer"
    authority = "ait1authority"
    escrow_addr = _escrow_address("job-1")
    account_map = {
        buyer: Account(chain_id="test", address=buyer, balance=1000, nonce=0),
        authority: Account(chain_id="test", address=authority, balance=100, nonce=0),
        escrow_addr: Account(chain_id="test", address=escrow_addr, balance=10, nonce=0),
    }
    tx = {
        "from": authority,
        "to": buyer,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_REFUND",
        "payload": {"job_id": "job-1"},
    }
    context = {
        "job-1": {
            "lock_version": 3,
            "expected_beneficiary": buyer,
            "escrow_addr": escrow_addr,
        }
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=3, escrow_context=context)
    assert delta.success
    assert delta.sender_balance_change == -1
    assert delta.recipient_balance_change == 10
    assert delta.recipient == buyer
    assert delta.extra_debits == {escrow_addr: -10}


def test_v3_escrow_release_rejects_wrong_beneficiary():
    buyer = "ait1buyer"
    provider = "ait1provider"
    authority = "ait1authority"
    escrow_addr = _escrow_address("job-1")
    account_map = {
        authority: Account(chain_id="test", address=authority, balance=100, nonce=0),
        escrow_addr: Account(chain_id="test", address=escrow_addr, balance=10, nonce=0),
    }
    tx = {
        "from": authority,
        "to": buyer,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "job-1"},
    }
    context = {
        "job-1": {
            "lock_version": 3,
            "expected_beneficiary": provider,
            "escrow_addr": escrow_addr,
        }
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=3, escrow_context=context)
    assert not delta.success
    assert "must pay" in delta.error


def test_v3_escrow_release_rejects_insufficient_escrow():
    provider = "ait1provider"
    authority = "ait1authority"
    escrow_addr = _escrow_address("job-1")
    account_map = {
        authority: Account(chain_id="test", address=authority, balance=100, nonce=0),
        escrow_addr: Account(chain_id="test", address=escrow_addr, balance=5, nonce=0),
    }
    tx = {
        "from": authority,
        "to": provider,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "job-1"},
    }
    context = {
        "job-1": {
            "lock_version": 3,
            "expected_beneficiary": provider,
            "escrow_addr": escrow_addr,
        }
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=3, escrow_context=context)
    assert not delta.success
    assert "has insufficient balance" in delta.error


def test_v2_escrow_release_uses_generic_path():
    """A v2 (lock_version < 3) ESCROW_RELEASE falls back to the generic transfer."""
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
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=2)
    assert delta.success
    assert delta.sender_balance_change == -11
    assert delta.recipient_balance_change == 10


def test_v3_escrow_release_env_fallback_authority(monkeypatch):
    """ESCROW_RELEASE_ADDRESS feeds the authority check when the settings field is empty."""
    provider = "ait1provider"
    wrong = "ait1wrong"
    escrow_addr = _escrow_address("job-1")
    account_map = {
        wrong: Account(chain_id="test", address=wrong, balance=100, nonce=0),
        escrow_addr: Account(chain_id="test", address=escrow_addr, balance=10, nonce=0),
    }
    tx = {
        "from": wrong,
        "to": provider,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "job-1"},
    }
    context = {
        "job-1": {
            "lock_version": 3,
            "expected_beneficiary": provider,
            "escrow_addr": escrow_addr,
        }
    }
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.setenv("ESCROW_RELEASE_ADDRESS", "ait1authority")
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=3, escrow_context=context)
    assert not delta.success
    assert "settlement authority" in delta.error


def test_escrow_release_context_authority_enforced():
    """The context-carried authority gates the sender — no env lookup needed."""
    provider = "ait1provider"
    authority = "ait1authority"
    wrong = "ait1wrong"
    escrow_addr = _escrow_address("job-1")
    account_map = {
        wrong: Account(chain_id="test", address=wrong, balance=100, nonce=0),
        authority: Account(chain_id="test", address=authority, balance=100, nonce=0),
        escrow_addr: Account(chain_id="test", address=escrow_addr, balance=10, nonce=0),
    }
    context = {
        "job-1": {
            "lock_version": 3,
            "expected_beneficiary": provider,
            "escrow_addr": escrow_addr,
            "settlement_authority": authority,
        }
    }
    base_tx = {
        "to": provider,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "job-1"},
    }
    bad = compute_state_delta(
        account_map, {**base_tx, "from": wrong}, "test", tx_hash="tx1", block_version=3, escrow_context=context
    )
    assert not bad.success
    assert "settlement authority" in bad.error
    good = compute_state_delta(
        account_map, {**base_tx, "from": authority}, "test", tx_hash="tx2", block_version=3, escrow_context=context
    )
    assert good.success, good.error


def test_v5_escrow_release_rejected_without_authority():
    """v5 fails closed: the context carries a resolved authority of None."""
    provider = "ait1provider"
    sender = "ait1sender"
    escrow_addr = _escrow_address("job-1")
    account_map = {
        sender: Account(chain_id="test", address=sender, balance=100, nonce=0),
        escrow_addr: Account(chain_id="test", address=escrow_addr, balance=10, nonce=0),
    }
    tx = {
        "from": sender,
        "to": provider,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "job-1"},
    }
    context = {
        "job-1": {
            "lock_version": 3,
            "expected_beneficiary": provider,
            "escrow_addr": escrow_addr,
            "settlement_authority": None,
        }
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=5, escrow_context=context)
    assert not delta.success
    assert "settlement authority" in delta.error


def test_v4_escrow_release_stays_lenient_without_authority(monkeypatch):
    """Pre-v5 replay compat: no authority anywhere → the release still applies."""
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    provider = "ait1provider"
    sender = "ait1sender"
    escrow_addr = _escrow_address("job-1")
    account_map = {
        sender: Account(chain_id="test", address=sender, balance=100, nonce=0),
        escrow_addr: Account(chain_id="test", address=escrow_addr, balance=10, nonce=0),
    }
    tx = {
        "from": sender,
        "to": provider,
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": "job-1"},
    }
    context = {
        "job-1": {
            "lock_version": 3,
            "expected_beneficiary": provider,
            "escrow_addr": escrow_addr,
            "settlement_authority": None,
        }
    }
    delta = compute_state_delta(account_map, tx, "test", tx_hash="tx1", block_version=4, escrow_context=context)
    assert delta.success, delta.error


def test_v5_bridge_credits_require_pseudo_sender():
    """v5: a bridge credit from anything but the pseudo-sender is forged."""
    recipient = "ait1recipient"
    for tx_type, expected_sender in (("BRIDGE_RELEASE", "bridge_release"), ("BRIDGE_REFUND", "bridge_refund")):
        legit = {"from": expected_sender, "to": recipient, "amount": 10, "value": 10, "fee": 0, "nonce": 0, "type": tx_type}
        delta = compute_state_delta({}, legit, "test", tx_hash="tx-ok", block_version=5)
        assert delta.success, delta.error
        forged = {**legit, "from": "ait1attacker"}
        delta = compute_state_delta({}, forged, "test", tx_hash="tx-bad", block_version=5)
        assert not delta.success
        assert "pseudo-sender" in delta.error


def test_v4_bridge_credit_stays_lenient_on_sender():
    """Pre-v5 replay compat: the sender check did not exist."""
    tx = {"from": "anything", "to": "ait1recipient", "amount": 10, "value": 10, "fee": 0, "nonce": 0, "type": "BRIDGE_RELEASE"}
    delta = compute_state_delta({}, tx, "test", tx_hash="tx-br", block_version=4)
    assert delta.success, delta.error
