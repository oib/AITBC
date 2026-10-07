"""v11: ESCROW_FEE_SWEEP drains a settled escrow's custody residue to the
governed fee recipient.

The consensus rule (design: TOPOLOGY/2026-10-04-fee-sink-design.md, Option B /
cadence (a)): from ``state_transition_v11_height`` the settlement authority may
sweep what remains in a job's derived custody account — the withheld platform
fee plus rounding dust v3 custody strands there — to the address pinned by the
on-chain ``escrow_fee_recipient`` chain parameter (env fallback
``ESCROW_FEE_RECIPIENT``). Below the gate the type name has no consensus
meaning: a block carrying it replays as the plain transfer it always was, so
sealed history is untouched.

These tests are deterministic — in-memory chain DB, fixed keys, no network.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from eth_utils import keccak

from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, Block, ChainParameter, Transaction
from aitbc_chain.config import ChainSettings, settings
from aitbc_chain.state.pure_state_transition import _escrow_address, compute_state_delta
from aitbc_chain.state.state_transition import (
    StateTransition,
    build_escrow_context,
    get_block_version_for_height,
)

CHAIN = "ait-test"

AUTHORITY_KEY = "0x" + "aa" * 32
STRANGER_KEY = "0x" + "5b" * 32
AUTHORITY = derive_ethereum_address(AUTHORITY_KEY)
STRANGER = derive_ethereum_address(STRANGER_KEY)
# Obviously synthetic test addresses — the real recipient is designated at
# deploy time and must never be hardcoded anywhere. canonical_address()
# gives the EIP-55 form the resolvers and address normalizers return.
FEE_RECIPIENT = canonical_address("0x" + "fe" * 20)
OTHER_RECIPIENT = canonical_address("0x" + "d1" * 20)

JOB = "sweep-job-1"


def _set(session, parameter: str, value: str) -> None:
    session.add(ChainParameter(chain_id=CHAIN, parameter=parameter, value=value))
    session.commit()


def _seed_custody(session, job_id: str = JOB, balance: int = 45_000) -> str:
    """Fund the derived custody account as a settled v3 lock would leave it."""
    addr = _escrow_address(job_id)
    session.add(Account(chain_id=CHAIN, address=addr, balance=balance, nonce=0))
    session.commit()
    return addr


def _sweep_tx(
    sender_key: str,
    recipient: str,
    value: int,
    *,
    nonce: int = 0,
    job_id: str = JOB,
    tx_type: str = "ESCROW_FEE_SWEEP",
    fee: int = DEFAULT_TX_FEE_UNITS,
) -> dict[str, Any]:
    sender = derive_ethereum_address(sender_key)
    tx: dict[str, Any] = {
        "from": sender,
        "to": recipient,
        "value": value,
        "fee": fee,
        "nonce": nonce,
        "type": tx_type,
        "chain_id": CHAIN,
        "payload": {"action": "escrow_fee_sweep", "job_id": job_id},
    }
    # The signed form mirrors _unsigned_tx_fields: every field except the
    # signature (``value`` stays — this shape carries no ``amount`` alias).
    signable = {k: v for k, v in tx.items() if k != "signature"}
    digest = "0x" + keccak(json.dumps(signable, sort_keys=True, separators=(",", ":")).encode()).hex()
    return {**tx, "signature": sign_transaction_hash(digest, sender_key)}


@pytest.fixture
def funded_authority(session):
    session.add(Account(chain_id=CHAIN, address=AUTHORITY, balance=1_000_000, nonce=0))
    session.add(Account(chain_id=CHAIN, address=STRANGER, balance=1_000_000, nonce=0))
    session.commit()
    return session


@pytest.fixture
def configured(session):
    """Both chain parameters set — the fully-wired v11 surface."""
    _set(session, "escrow_settlement_authority", AUTHORITY)
    _set(session, "escrow_fee_recipient", FEE_RECIPIENT)
    return session


def _apply(session, tx: dict[str, Any], tx_hash: str, *, block_version: int, block_height: int = 50_000):
    return StateTransition().apply_transaction(
        session, CHAIN, tx, tx_hash, block_version=block_version, block_height=block_height
    )


def _balance(session, address: str) -> int:
    account = session.get(Account, (CHAIN, address))
    return account.balance if account else 0


# ---------------------------------------------------------------------------
# Gate off: below v11 the type is a plain transfer, identical to any unknown
# type — sealed history keeps replaying byte-identically.
# ---------------------------------------------------------------------------


def test_below_gate_sweep_applies_as_plain_transfer(funded_authority, configured):
    """At v10 an ESCROW_FEE_SWEEP is an ordinary value transfer: sender pays
    value+fee, recipient credited, custody account untouched."""
    escrow_addr = _seed_custody(configured)
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 100)
    ok, msg = _apply(configured, tx, "sweep-v10", block_version=10)
    assert ok, msg
    assert _balance(configured, AUTHORITY) == 1_000_000 - 100 - DEFAULT_TX_FEE_UNITS
    assert _balance(configured, FEE_RECIPIENT) == 100
    assert _balance(configured, escrow_addr) == 45_000


def test_below_gate_sweep_matches_transfer_delta():
    """Replay equivalence: at v10 the pure path computes the identical delta for
    type ESCROW_FEE_SWEEP as for TRANSFER — the name carries no rule below the
    gate, so a historical block containing it replays byte-identically."""
    for tx_type in ("TRANSFER", "ESCROW_FEE_SWEEP"):
        account_map = {AUTHORITY: Account(chain_id=CHAIN, address=AUTHORITY, balance=1_000_000, nonce=0)}
        delta = compute_state_delta(
            account_map,
            _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 7, tx_type=tx_type),
            CHAIN,
            tx_hash=f"d-{tx_type}",
            block_version=10,
        )
        assert delta.success, delta.error
        assert delta.sender_balance_change == -(7 + DEFAULT_TX_FEE_UNITS)
        assert delta.recipient_balance_change == 7
        assert delta.sender_nonce_change == 1
        assert delta.extra_debits is None


def test_v11_pure_delta_fails_closed_without_authority():
    """Crossing the boundary: the same signed tx that is a plain transfer at
    v10 hits the v11 rule set at v11 — with no authority configured it fails
    closed."""
    sweep = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 7)
    account_map = {AUTHORITY: Account(chain_id=CHAIN, address=AUTHORITY, balance=1_000_000, nonce=0)}
    v10 = compute_state_delta(account_map, sweep, CHAIN, tx_hash="x10", block_version=10)
    assert v10.success, v10.error
    account_map = {AUTHORITY: Account(chain_id=CHAIN, address=AUTHORITY, balance=1_000_000, nonce=0)}
    v11 = compute_state_delta(account_map, sweep, CHAIN, tx_hash="x11", block_version=11)
    assert not v11.success
    assert "settlement authority" in v11.error


def test_v11_height_is_baked_at_35400(monkeypatch):
    """The baked default is consensus: a fresh settings object (no env, no env
    file) activates v11 at 35400 — a node built with no env line treats the
    type as a plain transfer below the boundary and applies the sweep rules
    at it."""
    monkeypatch.delenv("STATE_TRANSITION_V11_HEIGHT", raising=False)
    assert ChainSettings(_env_file=None).state_transition_v11_height == 35_400
    monkeypatch.setattr(settings, "state_transition_v11_height", 35_400)
    assert get_block_version_for_height(35_399) == 10
    assert get_block_version_for_height(35_400) == 11


def test_v11_env_still_overrides_the_baked_default(monkeypatch):
    """STATE_TRANSITION_V11_HEIGHT still wins over the baked default for a
    process that sets it."""
    monkeypatch.setenv("STATE_TRANSITION_V11_HEIGHT", "40000")
    assert ChainSettings(_env_file=None).state_transition_v11_height == 40_000


def test_v12_height_is_baked_at_37500(monkeypatch):
    """The baked default is consensus: a fresh settings object (no env, no env
    file) activates the v12 authority-parameter value checks at 37500 — a node
    built with no env line enforces them above the boundary and replays the
    lenient rule below it."""
    monkeypatch.delenv("STATE_TRANSITION_V12_HEIGHT", raising=False)
    assert ChainSettings(_env_file=None).state_transition_v12_height == 37_500


def test_v12_env_still_overrides_the_baked_default(monkeypatch):
    """STATE_TRANSITION_V12_HEIGHT still wins over the baked default for a
    process that sets it."""
    monkeypatch.setenv("STATE_TRANSITION_V12_HEIGHT", "40000")
    assert ChainSettings(_env_file=None).state_transition_v12_height == 40_000


def test_v12_version_boundary_with_baked_default(monkeypatch):
    """With the baked default the height ladder stamps 11 at 37499 and 12 at
    37500 — the exact activation boundary sealed on the fleet."""
    monkeypatch.delenv("STATE_TRANSITION_V12_HEIGHT", raising=False)
    monkeypatch.setattr(settings, "state_transition_v12_height", 37_500)
    assert get_block_version_for_height(37_499) == 11
    assert get_block_version_for_height(37_500) == 12


# ---------------------------------------------------------------------------
# Gate on: the v11 rule set.
# ---------------------------------------------------------------------------


def test_v11_sweep_drains_custody_to_fee_recipient(funded_authority, configured):
    """Happy path: custody account debited, recipient credited, sender pays
    only the fee, nonce +1 — the same delta shape as a v3 release."""
    escrow_addr = _seed_custody(configured)
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 45_000)
    ok, msg = _apply(configured, tx, "sweep-full", block_version=11)
    assert ok, msg
    assert _balance(configured, escrow_addr) == 0
    assert _balance(configured, FEE_RECIPIENT) == 45_000
    # Sender pays only the fee — never the swept value.
    assert _balance(configured, AUTHORITY) == 1_000_000 - DEFAULT_TX_FEE_UNITS
    assert configured.get(Account, (CHAIN, AUTHORITY)).nonce == 1


def test_v11_sweep_partial_residue(funded_authority, configured):
    escrow_addr = _seed_custody(configured, balance=29)
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 29)
    ok, msg = _apply(configured, tx, "sweep-dust", block_version=11)
    assert ok, msg
    assert _balance(configured, escrow_addr) == 0
    assert _balance(configured, FEE_RECIPIENT) == 29


def test_v11_sweep_rejects_wrong_sender(funded_authority, configured):
    _seed_custody(configured)
    tx = _sweep_tx(STRANGER_KEY, FEE_RECIPIENT, 100)
    ok, msg = StateTransition().validate_transaction(
        configured, CHAIN, tx, "sweep-wrong-sender", block_version=11, block_height=50_000
    )
    assert not ok
    assert "must be signed by settlement authority" in msg


def test_v11_sweep_rejects_wrong_recipient(funded_authority, configured):
    _seed_custody(configured)
    tx = _sweep_tx(AUTHORITY_KEY, OTHER_RECIPIENT, 100)
    ok, msg = StateTransition().validate_transaction(
        configured, CHAIN, tx, "sweep-wrong-recipient", block_version=11, block_height=50_000
    )
    assert not ok
    assert f"ESCROW_FEE_SWEEP must pay {FEE_RECIPIENT}" in msg


def test_v11_sweep_fails_closed_when_recipient_unset(funded_authority, session, monkeypatch):
    _set(session, "escrow_settlement_authority", AUTHORITY)
    _seed_custody(session)
    monkeypatch.setattr(settings, "escrow_fee_recipient", "")
    monkeypatch.delenv("ESCROW_FEE_RECIPIENT", raising=False)
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 100)
    ok, msg = StateTransition().validate_transaction(
        session, CHAIN, tx, "sweep-no-recipient", block_version=11, block_height=50_000
    )
    assert not ok
    assert "requires a fee recipient" in msg


def test_v11_sweep_fails_closed_when_authority_unset(funded_authority, session, monkeypatch):
    _set(session, "escrow_fee_recipient", FEE_RECIPIENT)
    _seed_custody(session)
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 100)
    ok, msg = StateTransition().validate_transaction(
        session, CHAIN, tx, "sweep-no-authority", block_version=11, block_height=50_000
    )
    assert not ok
    assert "requires a settlement authority" in msg


def test_v11_sweep_rejects_value_over_custody_balance(funded_authority, configured):
    escrow_addr = _seed_custody(configured, balance=100)
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 101)
    ok, msg = StateTransition().validate_transaction(
        configured, CHAIN, tx, "sweep-over", block_version=11, block_height=50_000
    )
    assert not ok
    assert "insufficient balance" in msg
    assert _balance(configured, escrow_addr) == 100


def test_v11_sweep_rejects_sender_unable_to_pay_fee(session):
    """The authority pays only the fee: an authority whose balance covers the
    sweep value but not the fee is still refused on the fee check."""
    broke_key = "0x" + "b0" * 32
    broke = derive_ethereum_address(broke_key)
    _set(session, "escrow_settlement_authority", broke)
    _set(session, "escrow_fee_recipient", FEE_RECIPIENT)
    _seed_custody(session)
    session.add(Account(chain_id=CHAIN, address=broke, balance=0, nonce=0))
    session.commit()
    tx = _sweep_tx(broke_key, FEE_RECIPIENT, 10)
    ok, msg = StateTransition().validate_transaction(session, CHAIN, tx, "sweep-broke", block_version=11, block_height=50_000)
    assert not ok
    assert "Insufficient balance for fee" in msg


def test_v11_sweep_requires_job_id(funded_authority, configured):
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 1)
    tx["payload"] = {"action": "escrow_fee_sweep"}
    # Re-sign after mutating the payload so the signature stays valid.
    signable = {k: v for k, v in tx.items() if k != "signature"}
    digest = "0x" + keccak(json.dumps(signable, sort_keys=True, separators=(",", ":")).encode()).hex()
    tx["signature"] = sign_transaction_hash(digest, AUTHORITY_KEY)
    ok, msg = StateTransition().validate_transaction(
        configured, CHAIN, tx, "sweep-no-job", block_version=11, block_height=50_000
    )
    assert not ok
    assert "payload must include job_id" in msg


def test_v11_sweep_v2_era_job_has_no_custody(funded_authority, configured):
    """A v2-era lock never funded a per-job account — the custody account is
    absent, so the balance check fails naturally (0 < value)."""
    # No custody account seeded: the job simply has no v3 custody.
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 1)
    ok, msg = StateTransition().validate_transaction(configured, CHAIN, tx, "sweep-v2", block_version=11, block_height=50_000)
    assert not ok
    assert "insufficient balance" in msg


def test_v11_sweep_sender_nonce_must_match(funded_authority, configured):
    _seed_custody(configured)
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 10, nonce=5)
    ok, msg = StateTransition().validate_transaction(
        configured, CHAIN, tx, "sweep-nonce", block_version=11, block_height=50_000
    )
    assert not ok
    assert "nonce" in msg.lower()


# ---------------------------------------------------------------------------
# Pure path parity: compute_state_delta with/without the prefetched context.
# ---------------------------------------------------------------------------


def _context(session, *txs):
    return build_escrow_context(session, CHAIN, [dict(t) for t in txs])


def test_pure_sweep_uses_prefetched_context(funded_authority, configured):
    escrow_addr = _seed_custody(configured, balance=500)
    sweep = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 500)
    ctx = _context(configured, sweep)
    assert ctx is not None and JOB in ctx
    assert ctx[JOB]["escrow_addr"] == escrow_addr
    assert ctx[JOB]["settlement_authority"] == AUTHORITY
    assert ctx[JOB]["fee_recipient"] == FEE_RECIPIENT
    account_map = {
        AUTHORITY: Account(chain_id=CHAIN, address=AUTHORITY, balance=1_000_000, nonce=0),
        escrow_addr: Account(chain_id=CHAIN, address=escrow_addr, balance=500, nonce=0),
    }
    delta = compute_state_delta(account_map, sweep, CHAIN, tx_hash="sweep-pure", block_version=11, escrow_context=ctx)
    assert delta.success
    assert delta.sender_balance_change == -DEFAULT_TX_FEE_UNITS
    assert delta.recipient_balance_change == 500
    assert delta.sender_nonce_change == 1
    assert delta.extra_debits == {escrow_addr: -500}


def test_pure_sweep_below_gate_is_generic_transfer(configured):
    account_map = {AUTHORITY: Account(chain_id=CHAIN, address=AUTHORITY, balance=1_000_000, nonce=0)}
    sweep = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 50)
    delta = compute_state_delta(account_map, sweep, CHAIN, tx_hash="sweep-old", block_version=10)
    assert delta.success
    assert delta.sender_balance_change == -(50 + DEFAULT_TX_FEE_UNITS)
    assert delta.extra_debits is None


def test_pure_sweep_context_free_falls_back_to_env(funded_authority, session, monkeypatch):
    """Without a context entry the pure path resolves the env fallback — the
    mempool-check shape; block application always carries the resolved context."""
    _seed_custody(session, balance=300)
    monkeypatch.setattr(settings, "escrow_settlement_authority", AUTHORITY)
    monkeypatch.setattr(settings, "escrow_fee_recipient", FEE_RECIPIENT)
    escrow_addr = _escrow_address(JOB)
    account_map = {
        AUTHORITY: Account(chain_id=CHAIN, address=AUTHORITY, balance=1_000_000, nonce=0),
        escrow_addr: Account(chain_id=CHAIN, address=escrow_addr, balance=300, nonce=0),
    }
    sweep = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 300)
    delta = compute_state_delta(account_map, sweep, CHAIN, tx_hash="sweep-env", block_version=11)
    assert delta.success
    assert delta.extra_debits == {escrow_addr: -300}


def test_pure_sweep_wrong_sender_and_recipient(configured):
    escrow_addr = _escrow_address(JOB)
    account_map = {
        AUTHORITY: Account(chain_id=CHAIN, address=AUTHORITY, balance=1_000_000, nonce=0),
        STRANGER: Account(chain_id=CHAIN, address=STRANGER, balance=1_000_000, nonce=0),
        escrow_addr: Account(chain_id=CHAIN, address=escrow_addr, balance=500, nonce=0),
    }
    ctx = {
        JOB: {
            "escrow_addr": escrow_addr,
            "settlement_authority": AUTHORITY,
            "fee_recipient": FEE_RECIPIENT,
        }
    }
    bad_sender = _sweep_tx(STRANGER_KEY, FEE_RECIPIENT, 100)
    delta = compute_state_delta(account_map, bad_sender, CHAIN, tx_hash="s1", block_version=11, escrow_context=ctx)
    assert not delta.success and "must be signed by settlement authority" in delta.error
    bad_recipient = _sweep_tx(AUTHORITY_KEY, OTHER_RECIPIENT, 100)
    delta = compute_state_delta(account_map, bad_recipient, CHAIN, tx_hash="s2", block_version=11, escrow_context=ctx)
    assert not delta.success and "must pay" in delta.error
    no_recipient_ctx = {JOB: {"escrow_addr": escrow_addr, "settlement_authority": AUTHORITY, "fee_recipient": None}}
    delta = compute_state_delta(
        account_map,
        _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 100),
        CHAIN,
        tx_hash="s3",
        block_version=11,
        escrow_context=no_recipient_ctx,
    )
    assert not delta.success and "requires a fee recipient" in delta.error
    no_authority_ctx = {JOB: {"escrow_addr": escrow_addr, "settlement_authority": None, "fee_recipient": FEE_RECIPIENT}}
    delta = compute_state_delta(
        account_map,
        _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 100),
        CHAIN,
        tx_hash="s4",
        block_version=11,
        escrow_context=no_authority_ctx,
    )
    assert not delta.success and "requires a settlement authority" in delta.error


def test_pure_sweep_over_balance_fails(configured):
    escrow_addr = _escrow_address(JOB)
    account_map = {
        AUTHORITY: Account(chain_id=CHAIN, address=AUTHORITY, balance=1_000_000, nonce=0),
        escrow_addr: Account(chain_id=CHAIN, address=escrow_addr, balance=10, nonce=0),
    }
    ctx = {JOB: {"escrow_addr": escrow_addr, "settlement_authority": AUTHORITY, "fee_recipient": FEE_RECIPIENT}}
    delta = compute_state_delta(
        account_map,
        _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 11),
        CHAIN,
        tx_hash="s5",
        block_version=11,
        escrow_context=ctx,
    )
    assert not delta.success and "insufficient balance" in delta.error


def test_pure_sweep_rw_set_includes_custody_account():
    from aitbc_chain.state.pure_state_transition import extract_read_write_sets

    read_set, write_set = extract_read_write_sets(
        {
            "from": AUTHORITY,
            "to": FEE_RECIPIENT,
            "type": "ESCROW_FEE_SWEEP",
            "payload": {"job_id": JOB},
        }
    )
    escrow_addr = _escrow_address(JOB)
    assert escrow_addr in read_set and escrow_addr in write_set
    assert AUTHORITY in write_set and FEE_RECIPIENT in write_set


# ---------------------------------------------------------------------------
# build_escrow_context: sweep indexing and the release+sweep merge.
# ---------------------------------------------------------------------------


def _seed_v3_lock(session, job_id: str, provider: str = "0x" + "77" * 20) -> None:
    session.add(
        Block(
            chain_id=CHAIN,
            height=10,
            hash="0xlockblock" + job_id,
            parent_hash="0x0",
            proposer="0x" + "11" * 20,
            block_metadata=json.dumps({"state_transition_version": 3}),
        )
    )
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash="0xlock" + job_id,
            block_height=10,
            sender="0x" + "66" * 20,
            recipient=_escrow_address(job_id),
            type="ESCROW_LOCK",
            payload={"job_id": job_id, "provider": provider},
            value=100,
        )
    )
    session.commit()


def test_context_indexes_sweep_without_lock(funded_authority, configured):
    """A sweep needs no ESCROW_LOCK — the custody account derives from job_id."""
    sweep = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 5)
    ctx = _context(configured, sweep)
    assert ctx is not None
    assert ctx[JOB]["tx_type"] == "ESCROW_FEE_SWEEP"
    assert ctx[JOB]["fee_recipient"] == FEE_RECIPIENT
    assert ctx[JOB]["escrow_addr"] == _escrow_address(JOB)


def test_context_merges_release_then_sweep(funded_authority, configured):
    """The designed cadence — a release followed by a sweep for the same job —
    must share one context entry, not force the sequential path."""
    _seed_v3_lock(configured, JOB)
    release = {
        "from": AUTHORITY,
        "to": "0x" + "77" * 20,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": JOB},
    }
    sweep = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 5)
    ctx = _context(configured, release, sweep)
    assert ctx is not None
    entry = ctx[JOB]
    assert entry["tx_type"] == "ESCROW_RELEASE"
    assert entry["lock_version"] == 3
    assert entry["fee_recipient"] == FEE_RECIPIENT
    assert entry["settlement_authority"] == AUTHORITY


def test_context_merges_sweep_then_release(funded_authority, configured):
    """Same batch, opposite order — the merge must be order-independent."""
    _seed_v3_lock(configured, JOB)
    sweep = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 5)
    release = {
        "from": AUTHORITY,
        "to": "0x" + "77" * 20,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": JOB},
    }
    ctx = _context(configured, sweep, release)
    assert ctx is not None
    entry = ctx[JOB]
    assert entry["tx_type"] == "ESCROW_RELEASE"
    assert entry["lock_version"] == 3
    assert entry["fee_recipient"] == FEE_RECIPIENT


def test_context_release_and_refund_still_forces_sequential(funded_authority, configured):
    """Unchanged pre-v11 rule: release+refund for one job stays sequential even
    when a sweep rides along — the sequential path applies its own rules."""
    _seed_v3_lock(configured, JOB)
    release = {"from": AUTHORITY, "to": "0x" + "77" * 20, "type": "ESCROW_RELEASE", "payload": {"job_id": JOB}}
    refund = {"from": AUTHORITY, "to": "0x" + "66" * 20, "type": "ESCROW_REFUND", "payload": {"job_id": JOB}}
    sweep = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 5)
    assert _context(configured, release, refund, sweep) is None
    assert _context(configured, release, sweep, refund) is None


def test_context_sweep_entry_keeps_env_resolutions(funded_authority, session, monkeypatch):
    """Context carries the resolved chain-level params; with no on-chain row the
    builder resolves the env fallback for block_height=None callers."""
    monkeypatch.setattr(settings, "escrow_settlement_authority", AUTHORITY)
    monkeypatch.setattr(settings, "escrow_fee_recipient", FEE_RECIPIENT)
    sweep = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 5)
    ctx = build_escrow_context(session, CHAIN, [sweep])
    assert ctx is not None
    assert ctx[JOB]["settlement_authority"] == AUTHORITY
    assert ctx[JOB]["fee_recipient"] == FEE_RECIPIENT


# ---------------------------------------------------------------------------
# Adversarial surface (Task C review): the consensus rule bounds the sweep by
# the custody account's balance — and only that. These tests pin down the
# exact preconditions the apply branch does NOT enforce, so a future
# tightening is a deliberate, test-visible change rather than a silent one.
# ---------------------------------------------------------------------------


def test_v11_sweep_applies_to_never_settled_custody(funded_authority, configured):
    """No settledness precondition: custody that was funded by a lock but never
    released still sweeps. The apply branch verifies only signer, recipient
    and balance (design §4.7: the balance is the only consensus bound) — the
    authority's key can drain a still-locked job's funds to the fee recipient
    before any settlement leg exists."""
    escrow_addr = _seed_custody(configured, balance=12_345)
    # No ESCROW_LOCK/RELEASE/REFUND rows exist for this job at all.
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 12_345)
    ok, msg = _apply(configured, tx, "sweep-locked", block_version=11)
    assert ok, msg  # characterization: not gated on a prior settlement
    assert _balance(configured, escrow_addr) == 0
    assert _balance(configured, FEE_RECIPIENT) == 12_345


def test_v11_second_sweep_same_job_drains_remainder(funded_authority, configured):
    """No once-only invariant: a partial first sweep leaves residue reachable
    by a second sweep — two ESCROW_FEE_SWEEP legs for one job both apply.
    Harmless only because the route asks for the full remainder; a partial
    first sweep is not a protocol violation."""
    escrow_addr = _seed_custody(configured, balance=10_000)
    first = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 7_000, nonce=0)
    ok, msg = _apply(configured, first, "sweep-1", block_version=11)
    assert ok, msg
    second = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 3_000, nonce=1)
    ok, msg = _apply(configured, second, "sweep-2", block_version=11)
    assert ok, msg  # characterization: nothing marks a job swept once
    assert _balance(configured, escrow_addr) == 0
    assert _balance(configured, FEE_RECIPIENT) == 10_000


def test_v11_sweep_value_bounded_only_by_custody_balance(funded_authority, configured):
    """The apply branch accepts any value <= custody balance — it does not
    require the sweep to equal the residue the settlement legs left. A sweep
    naming less than the remainder validates; the leftover stays sweepable."""
    escrow_addr = _seed_custody(configured, balance=1_000)
    tx = _sweep_tx(AUTHORITY_KEY, FEE_RECIPIENT, 400)
    ok, msg = _apply(configured, tx, "sweep-part", block_version=11)
    assert ok, msg
    assert _balance(configured, escrow_addr) == 600


def test_v11_block_resolves_by_local_env_not_stamp(monkeypatch):
    """Above the v8 threshold the recorded stamp is advisory: the applied
    version comes from the local activation settings, not the block. A node
    missing the v11 env pin resolves a v11-stamped block to v10 — every sweep
    inside it then applies as a plain transfer (see
    test_below_gate_sweep_applies_as_plain_transfer), diverging from
    env-pinned nodes. Until the height is baked into config.py, fleet
    consensus on a sweep block depends on every node carrying the same
    STATE_TRANSITION_V11_HEIGHT."""
    from aitbc_chain.state.state_transition import get_block_version

    monkeypatch.setattr(settings, "state_transition_v8_height", 30_000)
    monkeypatch.setattr(settings, "state_transition_v9_height", 31_000)
    monkeypatch.setattr(settings, "state_transition_v10_height", 33_000)
    monkeypatch.setattr(settings, "state_transition_v11_height", 35_400)
    block = {"block_metadata": {"state_transition_version": 11}}
    assert get_block_version(block, 35_400) == 11
    # Same stamped block on a node without the env pin -> v10 rule set.
    monkeypatch.setattr(settings, "state_transition_v11_height", None)
    assert get_block_version(block, 35_400) == 10
