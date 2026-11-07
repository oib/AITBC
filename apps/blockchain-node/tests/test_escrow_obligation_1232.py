"""v23 (R12-05-F1/#1232 + R14-06-F1/#1230): escrow obligation bound.

Custody balance is NOT settlement authorization. From
``state_transition_v23_height``:

- ``obligation`` = Σ applied ``ESCROW_LOCK.value`` for the job
- ``settled``    = Σ applied ``ESCROW_RELEASE``/``ESCROW_REFUND``.value
- ``remaining``  = obligation − settled

``ESCROW_RELEASE``/``ESCROW_REFUND`` may pay at most ``remaining`` —
third-party transfers into the custody address never raise entitlement.
``ESCROW_FEE_SWEEP`` may take only ``custody − remaining`` (residue).
Locks/settlements with unparseable ``value`` fail closed as unbounded
obligation; ambiguous multi-lock beneficiaries refuse rather than guess.

Below the gate every rule is bit-for-bit the old behavior — the exploit
sequence that v23 rejects still applies at v22.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from eth_utils import keccak

from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc_chain.base_models import Account, ChainParameter, Transaction
from aitbc_chain.config import settings
from aitbc_chain.state.admission_authority import sender_authority_error
from aitbc_chain.state.state_transition import (
    StateTransition,
    _escrow_address,
    build_escrow_context,
)

CHAIN = "ait-test"
AUTHORITY_KEY = "0x" + "aa" * 32
BUYER_KEY = "0x" + "11" * 32
THIRD_PARTY_KEY = "0x" + "44" * 32
AUTHORITY = derive_ethereum_address(AUTHORITY_KEY)
BUYER = derive_ethereum_address(BUYER_KEY)
PROVIDER = derive_ethereum_address("0x" + "22" * 32)
PROVIDER2 = derive_ethereum_address("0x" + "33" * 32)
THIRD_PARTY = derive_ethereum_address(THIRD_PARTY_KEY)
FEE_RECIPIENT = derive_ethereum_address("0x" + "fe" * 32)

JOB = "job-obl-1"
LOCK_VALUE = 100


def _set(session, parameter: str, value: str) -> None:
    session.add(ChainParameter(chain_id=CHAIN, parameter=parameter, value=value))
    session.commit()


@pytest.fixture
def session():
    from sqlalchemy import create_engine
    from sqlmodel import Session
    from aitbc_chain.metadata import chain_metadata

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


@pytest.fixture
def funded(session):
    for addr, bal in ((AUTHORITY, 1_000_000), (BUYER, 10_000), (PROVIDER, 0), (PROVIDER2, 0), (THIRD_PARTY, 10_000)):
        session.add(Account(chain_id=CHAIN, address=addr, balance=bal, nonce=0))
    _set(session, "escrow_settlement_authority", AUTHORITY)
    _set(session, "escrow_fee_recipient", FEE_RECIPIENT)
    session.commit()
    return session


_KEYS = {AUTHORITY: AUTHORITY_KEY, BUYER: BUYER_KEY, THIRD_PARTY: THIRD_PARTY_KEY}


def _tx(frm: str, to: str, value: int, tx_type: str, payload: dict, nonce: int = 0, fee: int = 0) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": frm,
        "to": to,
        "value": value,
        "fee": fee,
        "nonce": nonce,
        "type": tx_type,
        "chain_id": CHAIN,
        "payload": payload,
    }
    key = _KEYS.get(frm)
    if key is not None:
        signable = {k: v for k, v in tx.items() if k != "signature"}
        digest = "0x" + keccak(json.dumps(signable, sort_keys=True, separators=(",", ":")).encode()).hex()
        tx["signature"] = sign_transaction_hash(digest, key)
    return tx


def _lock_tx(job_id: str = JOB, amount: int = LOCK_VALUE, provider: str = PROVIDER, nonce: int = 0) -> dict[str, Any]:
    return _tx(BUYER, AUTHORITY, amount, "ESCROW_LOCK", {"job_id": job_id, "provider": provider}, nonce=nonce)


def _release_tx(job_id: str = JOB, to: str = PROVIDER, amount: int = 60, nonce: int = 0) -> dict[str, Any]:
    return _tx(AUTHORITY, to, amount, "ESCROW_RELEASE", {"job_id": job_id, "action": "escrow_release"}, nonce=nonce)


def _refund_tx(job_id: str = JOB, to: str = BUYER, amount: int = 40, nonce: int = 0) -> dict[str, Any]:
    return _tx(AUTHORITY, to, amount, "ESCROW_REFUND", {"job_id": job_id, "action": "escrow_refund"}, nonce=nonce)


def _sweep_tx(job_id: str = JOB, amount: int = 1, nonce: int = 0) -> dict[str, Any]:
    return _tx(
        AUTHORITY, FEE_RECIPIENT, amount, "ESCROW_FEE_SWEEP", {"job_id": job_id, "action": "escrow_fee_sweep"}, nonce=nonce
    )


def _record(
    session,
    tx_data: dict[str, Any],
    tx_hash: str,
    *,
    block_height: int = 100,
    status: str = "confirmed",
    tx_type: str | None = None,
    value: Any = "KEEP",
) -> None:
    """Persist the applied-tx row the way block sealing does."""
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            block_height=block_height,
            sender=tx_data["from"],
            recipient=tx_data["to"],
            payload=tx_data.get("payload") or {},
            value=tx_data.get("value", 0) if value == "KEEP" else value,
            fee=tx_data.get("fee", 0),
            nonce=tx_data.get("nonce", 0),
            type=tx_type or tx_data.get("type", "TRANSFER"),
            status=status,
            timestamp=datetime.now(UTC).isoformat(),
        )
    )
    session.commit()


def _apply(
    session, tx: dict[str, Any], tx_hash: str, *, block_version: int = 23, block_height: int = 200, skip_dedup: bool = False
):
    return StateTransition().apply_transaction(
        session, CHAIN, tx, tx_hash, block_version=block_version, block_height=block_height, skip_dedup=skip_dedup
    )


def _validate(
    session, tx: dict[str, Any], tx_hash: str, *, block_version: int = 23, block_height: int = 200, skip_dedup: bool = False
):
    return StateTransition().validate_transaction(
        session, CHAIN, tx, tx_hash, block_version=block_version, block_height=block_height, skip_dedup=skip_dedup
    )


def _balance(session, address: str) -> int:
    account = session.get(Account, (CHAIN, address))
    return account.balance if account else 0


def _fund_lock(session, job_id: str = JOB, amount: int = LOCK_VALUE, provider: str = PROVIDER) -> str:
    """Apply a real v3 ESCROW_LOCK and record its sealed tx row."""
    tx = _lock_tx(job_id, amount, provider)
    ok, msg = _apply(session, tx, f"lock-{job_id}", block_version=3, block_height=100)
    assert ok, msg
    _record(session, tx, f"lock-{job_id}", block_height=100)
    return _escrow_address(job_id)


def _seal_settlement(session, tx: dict[str, Any], tx_hash: str, nonce: int) -> None:
    """Record an already-applied settlement as a confirmed sealed tx."""
    _record(session, tx, tx_hash, block_height=200)


# ---------------------------------------------------------------------------
# Release/refund obligation bound
# ---------------------------------------------------------------------------


def test_v23_release_within_obligation_accepted(funded):
    escrow = _fund_lock(funded)
    tx = _release_tx(amount=60)
    ok, msg = _apply(funded, tx, "rel-1")
    assert ok, msg
    assert _balance(funded, escrow) == 40
    assert _balance(funded, PROVIDER) == 60


def test_v23_release_above_obligation_rejected(funded):
    _fund_lock(funded)
    ok, msg = _validate(funded, _release_tx(amount=140), "rel-over")
    assert not ok
    assert "exceeds remaining obligation 100" in msg


def test_v23_third_party_tip_does_not_raise_entitlement(funded):
    """#1232 repro: lock 100 → release 60 → +100 third-party tip → release 140
    must still fail — custody is not entitlement."""
    escrow = _fund_lock(funded)
    rel = _release_tx(amount=60, nonce=0)
    ok, msg = _apply(funded, rel, "rel-60")
    assert ok, msg
    _seal_settlement(funded, rel, "rel-60", 0)
    # Third party tips the custody account directly.
    funded.get(Account, (CHAIN, escrow)).balance += 100
    funded.commit()
    # Custody is now 140 but remaining obligation is only 40.
    ok, msg = _validate(funded, _release_tx(amount=140, nonce=1), "rel-140")
    assert not ok
    assert "exceeds remaining obligation 40" in msg
    # The true remainder still pays out.
    ok, msg = _apply(funded, _release_tx(amount=40, nonce=1), "rel-40")
    assert ok, msg
    assert _balance(funded, escrow) == 100  # 40 obligation + 100 tip remain


def test_v23_partial_releases_aggregate_bounded(funded):
    _fund_lock(funded)
    for i, amount in enumerate((60, 40)):
        tx = _release_tx(amount=amount, nonce=i)
        ok, msg = _apply(funded, tx, f"rel-p{i}")
        assert ok, msg
        _seal_settlement(funded, tx, f"rel-p{i}", i)
    # Aggregate settled = 100 = obligation; nothing remains.
    ok, msg = _validate(funded, _release_tx(amount=1, nonce=2), "rel-p2")
    assert not ok
    assert "exceeds remaining obligation 0" in msg


def test_v23_refund_after_release_bounded(funded):
    _fund_lock(funded)
    rel = _release_tx(amount=60, nonce=0)
    ok, msg = _apply(funded, rel, "rel-r1")
    assert ok, msg
    _seal_settlement(funded, rel, "rel-r1", 0)
    # Refund may only take what release left: 40.
    ok, msg = _validate(funded, _refund_tx(amount=50, nonce=1), "ref-over")
    assert not ok
    assert "exceeds remaining obligation 40" in msg
    ok, msg = _apply(funded, _refund_tx(amount=40, nonce=1), "ref-40")
    assert ok, msg
    # BUYER paid the 100 lock and got the 40 refund back.
    assert _balance(funded, BUYER) == 10_000 - LOCK_VALUE + 40


def test_v23_replay_revalidation_does_not_double_settle(funded):
    """Re-validating an already-sealed settlement excludes itself from
    ``settled`` — the same tx passes again (reorg/replay determinism)
    while a *different* tx sees the reduced remainder."""
    escrow = _fund_lock(funded)
    rel = _release_tx(amount=60, nonce=0)
    ok, msg = _apply(funded, rel, "rel-sealed")
    assert ok, msg
    _seal_settlement(funded, rel, "rel-sealed", 0)
    # Top custody back up so the balance check doesn't mask the obligation
    # verdict — this test isolates the settled-exclusion semantics.
    funded.get(Account, (CHAIN, escrow)).balance += 60
    funded.commit()
    # Same tx hash, revalidated (skip_dedup mirrors block re-import): its
    # own sealed row must not count against it. The account nonce has
    # advanced, so the revalidation carries the current nonce — the
    # obligation exclusion keys on tx_hash, not tx identity.
    rel_re = _release_tx(amount=60, nonce=1)
    ok, msg = _validate(funded, rel_re, "rel-sealed", skip_dedup=True)
    assert ok, msg
    # A fresh 60-release now sees only 40 remaining.
    ok, msg = _validate(funded, _release_tx(amount=60, nonce=1), "rel-new")
    assert not ok
    assert "exceeds remaining obligation 40" in msg


def test_v23_unbounded_lock_value_fails_closed(funded):
    """A lock row with unparseable value is treated as outstanding
    obligation — settlements refuse rather than under-count."""
    _fund_lock(funded)
    bad = _lock_tx("job-bad", 50)
    _record(funded, bad, "lock-bad", block_height=101, value="not-a-number")
    ok, msg = _validate(funded, _release_tx(job_id="job-bad", amount=1), "rel-bad")
    assert not ok
    assert "unbounded obligation" in msg


def test_v23_ambiguous_multi_lock_beneficiary_refused(funded):
    """Two locks for one job paying different providers → release refuses
    rather than guessing (Director Q3)."""
    _fund_lock(funded, provider=PROVIDER)
    tx2 = _lock_tx(amount=50, provider=PROVIDER2, nonce=1)
    ok, msg = _apply(funded, tx2, "lock-2", block_version=3, block_height=101)
    assert ok, msg
    _record(funded, tx2, "lock-2", block_height=101)
    ok, msg = _validate(funded, _release_tx(amount=10), "rel-amb")
    assert not ok
    assert "ambiguous beneficiary" in msg


# ---------------------------------------------------------------------------
# Fee sweep residue-only bound (#1230)
# ---------------------------------------------------------------------------


def test_v23_sweep_cannot_touch_locked_obligation(funded):
    """Custody == obligation → residue 0 → any sweep refuses."""
    _fund_lock(funded)
    ok, msg = _validate(funded, _sweep_tx(amount=1), "sweep-1")
    assert not ok
    assert "exceeds residue 0" in msg


def test_v23_sweep_takes_residue_only(funded):
    """After a partial release + third-party tip, sweep is bounded by
    custody − remaining obligation."""
    escrow = _fund_lock(funded)
    rel = _release_tx(amount=60, nonce=0)
    ok, msg = _apply(funded, rel, "rel-s1")
    assert ok, msg
    _seal_settlement(funded, rel, "rel-s1", 0)
    funded.get(Account, (CHAIN, escrow)).balance += 50  # tip
    funded.commit()
    # custody 90, remaining obligation 40 → residue 50.
    ok, msg = _validate(funded, _sweep_tx(amount=51, nonce=1), "sweep-51")
    assert not ok
    assert "exceeds residue 50" in msg
    ok, msg = _apply(funded, _sweep_tx(amount=50, nonce=1), "sweep-50")
    assert ok, msg
    assert _balance(funded, escrow) == 40  # obligation fully preserved


# ---------------------------------------------------------------------------
# Gate + context behavior
# ---------------------------------------------------------------------------


def test_below_v23_gate_old_semantics_preserved(funded):
    """The #1232 exploit still applies at v22 — the gate is what changes
    the verdict, proving replay safety for sealed history."""
    escrow = _fund_lock(funded)
    rel = _release_tx(amount=60, nonce=0)
    ok, msg = _apply(funded, rel, "rel-v22", block_version=22, block_height=199)
    assert ok, msg
    _record(funded, rel, "rel-v22", block_height=199)
    funded.get(Account, (CHAIN, escrow)).balance += 100
    funded.commit()
    # v22: balance check only — 140 <= custody 140 → accepted (old bug,
    # preserved for replay of pre-activation blocks).
    ok, msg = _validate(funded, _release_tx(amount=140, nonce=1), "rel-v22b", block_version=22, block_height=200)
    assert ok, msg


def test_v23_multi_settlement_batch_falls_back_sequential(funded, monkeypatch):
    """Two settlement txs for one job cannot share a static obligation
    snapshot — build_escrow_context returns None at v23 heights so the
    batch goes sequential; below the gate the old merge behavior stays."""
    monkeypatch.setattr(settings, "state_transition_v23_height", 150)
    _fund_lock(funded)
    txs = [_release_tx(amount=10, nonce=0), _release_tx(amount=10, nonce=1)]
    assert build_escrow_context(funded, CHAIN, txs, block_height=200) is None
    # Below the gate: same batch still builds context (legacy merge).
    ctx = build_escrow_context(funded, CHAIN, txs, block_height=140)
    assert ctx is not None and JOB in ctx


def test_v23_context_carries_obligation_fields(funded, monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v23_height", 150)
    _fund_lock(funded)
    ctx = build_escrow_context(funded, CHAIN, [_release_tx(amount=10)], block_height=200)
    assert ctx is not None
    entry = ctx[JOB]
    assert entry["remaining_obligation"] == 100
    assert entry["obligation_unbounded"] is False


def test_v23_door_mirrors_obligation_bound(funded):
    """admission_authority refuses at the door what apply would refuse."""
    _fund_lock(funded)
    err = sender_authority_error(
        funded,
        CHAIN,
        "ESCROW_RELEASE",
        AUTHORITY,
        block_version=23,
        block_height=200,
        recipient=PROVIDER,
        payload={"job_id": JOB},
        fee=0,
        value=140,
    )
    assert err is not None and "exceeds remaining obligation" in err
    err = sender_authority_error(
        funded,
        CHAIN,
        "ESCROW_RELEASE",
        AUTHORITY,
        block_version=23,
        block_height=200,
        recipient=PROVIDER,
        payload={"job_id": JOB},
        fee=0,
        value=60,
    )
    assert err is None
