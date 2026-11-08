"""v23 governed fee allowance (#1261, option E; operator ruling comment 19157).

v23's first sweep rule (``custody - remaining``) refused the designed fee leg:
a normally settled escrow is ``lock L -> release ~97.5% L -> sweep ~2.5% L`` and
the chain records no fee split, so after the release custody == remaining and
the sweep ceiling was 0. The amendment (v23 is still unarmed, so no replay
shim): a sweep may also take up to

    allowance = lock * escrow_fee_cap_bps / 10000 - already_swept

out of the remaining obligation, ``escrow_fee_cap_bps`` being a chain parameter
that defaults to 300 (3%), and only once the job has settled (``settled > 0``).
Ceiling = ``custody - max(0, remaining - allowance)``.

Pinned here at every place the bound is enforced: ``validate_transaction``
(apply), the admission door, and the pure parallel-apply path.
"""

from __future__ import annotations

import json
import os
import random
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
from aitbc_chain.state.pure_state_transition import (
    DEFAULT_ESCROW_FEE_CAP_BPS,
    _escrow_v23_sweep_obligation_error,
    escrow_sweep_ceiling,
)
from aitbc_chain.state.state_transition import _escrow_fee_cap_bps

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


# Live-shaped job (node2 bc-2 census, #1261): lock 360000, release 351000, sweep 9000.
LIVE_LOCK = 360_000
LIVE_RELEASE = 351_000
LIVE_SWEEP = 9_000


@pytest.fixture
def rich(funded):
    funded.get(Account, (CHAIN, BUYER)).balance = 10_000_000
    funded.commit()
    return funded


def _settle_live_shape(session, *, release: int = LIVE_RELEASE, job_id: str = JOB, lock: int = LIVE_LOCK) -> str:
    escrow = _fund_lock(session, job_id=job_id, amount=lock)
    rel = _release_tx(job_id=job_id, amount=release, nonce=0)
    ok, msg = _apply(session, rel, f"rel-{job_id}")
    assert ok, msg
    _seal_settlement(session, rel, f"rel-{job_id}", 0)
    return escrow


def _door(session, value: int, job_id: str = JOB, block_version: int = 23) -> str | None:
    return sender_authority_error(
        session,
        CHAIN,
        "ESCROW_FEE_SWEEP",
        AUTHORITY,
        block_version=block_version,
        block_height=200,
        recipient=FEE_RECIPIENT,
        payload={"job_id": job_id},
        fee=0,
        value=value,
    )


# ---------------------------------------------------------------------------
# The live shape
# ---------------------------------------------------------------------------


def test_live_shape_fee_sweep_accepted_at_v23(rich):
    """The reproduction from #1261: refused by the first v23 rule, accepted now."""
    escrow = _settle_live_shape(rich)
    assert _balance(rich, escrow) == LIVE_SWEEP
    ok, msg = _validate(rich, _sweep_tx(amount=LIVE_SWEEP, nonce=1), "sweep-live")
    assert ok, msg
    ok, msg = _apply(rich, _sweep_tx(amount=LIVE_SWEEP, nonce=1), "sweep-live")
    assert ok, msg
    assert _balance(rich, escrow) == 0
    assert _balance(rich, FEE_RECIPIENT) == LIVE_SWEEP


def test_live_shape_fee_sweep_unchanged_at_v22(rich):
    """Below the gate nothing changed: the sweep validated before and after."""
    _settle_live_shape(rich)
    ok, msg = _validate(rich, _sweep_tx(amount=LIVE_SWEEP, nonce=1), "sweep-v22", block_version=22, block_height=199)
    assert ok, msg


@pytest.mark.parametrize(
    ("lock", "released", "swept"),
    [
        (360_000, 351_000, 9_000),
        (1_800_000, 1_755_000, 45_000),
        (60_000, 58_500, 1_500),
        (60_000, 58_501, 1_499),
        (36_000, 35_100, 900),
        (152_434, 148_623, 3_811),
    ],
)
def test_every_live_settled_shape_is_sweepable(rich, lock, released, swept):
    """Each row of the #1261 census table fits under the 3% default cap."""
    _settle_live_shape(rich, release=released, lock=lock)
    ok, msg = _validate(rich, _sweep_tx(amount=swept, nonce=1), "sweep-row")
    assert ok, msg
    assert _door(rich, swept) is None


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


def test_sweep_is_capped_at_the_allowance(rich):
    """Lock 360000 released down to 345000 leaves 15000 in custody; the 3%
    cap is 10800, so 10800 sweeps and 10801 does not."""
    _settle_live_shape(rich, release=345_000)
    ok, msg = _validate(rich, _sweep_tx(amount=10_801, nonce=1), "sweep-over")
    assert not ok
    assert "exceeds sweepable 10800" in msg
    ok, msg = _validate(rich, _sweep_tx(amount=10_800, nonce=1), "sweep-cap")
    assert ok, msg


def test_no_allowance_before_anything_settled(rich):
    """settled>0 guard: the authority cannot pull the fee out of an unsettled lock."""
    _fund_lock(rich, amount=LIVE_LOCK)
    ok, msg = _validate(rich, _sweep_tx(amount=1, nonce=0), "sweep-unsettled")
    assert not ok
    assert "exceeds sweepable 0" in msg
    assert _door(rich, 1) is not None


def test_allowance_shrinks_by_what_was_already_swept(rich):
    """allowance = cap - already_swept. Lock 100000, release 90000, custody 10000,
    cap 3000: sweep 2000 seals, then the next sweep is held to what is left."""
    escrow = _settle_live_shape(rich, release=90_000, lock=100_000)
    sweep = _sweep_tx(amount=2_000, nonce=1)
    ok, msg = _apply(rich, sweep, "sweep-a")
    assert ok, msg
    _record(rich, sweep, "sweep-a", block_height=200)
    assert _balance(rich, escrow) == 8_000
    ok, msg = _validate(rich, _sweep_tx(amount=1_000, nonce=2), "sweep-b")
    # Conservative by design (the ruled formula): a prior sweep reduces the
    # allowance without also discharging the obligation, so split sweeps are
    # not supported at v23 — fail closed, never over-pay. Live fee legs are
    # a single sweep.
    assert not ok
    assert "exceeds sweepable" in msg


def test_unbounded_sweep_history_fails_closed(rich):
    """A sealed sweep row with an unparseable value cannot be counted, so the
    state is unbounded and the sweep refuses."""
    _settle_live_shape(rich)
    bad = _sweep_tx(amount=1, nonce=1)
    _record(rich, bad, "sweep-bad", block_height=200, value="not-a-number")
    ok, msg = _validate(rich, _sweep_tx(amount=LIVE_SWEEP, nonce=1), "sweep-next")
    assert not ok
    assert "unbounded obligation" in msg


# ---------------------------------------------------------------------------
# The chain parameter
# ---------------------------------------------------------------------------


def test_cap_defaults_to_300_bps(session):
    assert DEFAULT_ESCROW_FEE_CAP_BPS == 300
    assert _escrow_fee_cap_bps(session, CHAIN, 200) == 300


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("100", 100), ("0", 0), (" 250 ", 250), ("10000", 10_000), ("abc", 0), ("-1", 0), ("10001", 0), ("", 0), ("2.5", 0)],
)
def test_cap_chain_parameter_is_validated_and_fails_closed(session, raw, expected):
    _set(session, "escrow_fee_cap_bps", raw)
    assert _escrow_fee_cap_bps(session, CHAIN, 200) == expected


def test_lower_governed_cap_refuses_the_live_shape(rich):
    """The cap is governed, not baked: at 100 bps (1%) the 9000 fee leg exceeds
    the 3600 allowance, so the sweep is refused."""
    _set(rich, "escrow_fee_cap_bps", "100")
    _settle_live_shape(rich)
    ok, msg = _validate(rich, _sweep_tx(amount=LIVE_SWEEP, nonce=1), "sweep-1pct")
    assert not ok
    assert "exceeds sweepable 3600" in msg


def test_zero_cap_is_the_plain_residue_rule(rich):
    _set(rich, "escrow_fee_cap_bps", "0")
    _settle_live_shape(rich)
    ok, msg = _validate(rich, _sweep_tx(amount=1, nonce=1), "sweep-zero")
    assert not ok
    assert "exceeds sweepable 0" in msg


def test_cap_is_height_scoped(session):
    """A value that takes effect after the validated height does not apply."""
    from aitbc_chain.base_models import ChainParameterHistory

    session.add(ChainParameter(chain_id=CHAIN, parameter="escrow_fee_cap_bps", value="900", applied_height=500))
    session.add(ChainParameterHistory(chain_id=CHAIN, parameter="escrow_fee_cap_bps", value="900", applied_height=500))
    session.commit()
    assert _escrow_fee_cap_bps(session, CHAIN, 499) == 300
    assert _escrow_fee_cap_bps(session, CHAIN, 500) == 900


# ---------------------------------------------------------------------------
# The ceiling function and the other enforcement points
# ---------------------------------------------------------------------------


def test_ceiling_formula():
    assert escrow_sweep_ceiling(custody=9_000, remaining=9_000, fee_allowance=10_800) == 9_000
    assert escrow_sweep_ceiling(custody=9_000, remaining=9_000, fee_allowance=0) == 0
    assert escrow_sweep_ceiling(custody=15_000, remaining=15_000, fee_allowance=10_800) == 10_800
    assert escrow_sweep_ceiling(custody=14_000, remaining=9_000, fee_allowance=3_000) == 8_000  # residue 5000 + allowance 3000
    assert escrow_sweep_ceiling(custody=0, remaining=9_000, fee_allowance=3_000) < 0  # never sweepable


def test_door_mirrors_apply(rich):
    _settle_live_shape(rich, release=345_000)
    assert _door(rich, 10_800) is None
    err = _door(rich, 10_801)
    assert err is not None and "exceeds sweepable 10800" in err
    assert _door(rich, 10_801, block_version=22) is None  # below the gate: no bound


def test_context_carries_the_allowance_and_the_pure_path_honours_it(rich, monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v23_height", 150)
    escrow = _settle_live_shape(rich, release=345_000)
    ctx = build_escrow_context(rich, CHAIN, [_sweep_tx(amount=10_800, nonce=1)], block_height=200)
    assert ctx is not None
    entry = ctx[JOB]
    assert entry["fee_allowance"] == 10_800
    assert entry["remaining_obligation"] == 15_000
    accounts = {escrow: rich.get(Account, (CHAIN, escrow))}
    assert _escrow_v23_sweep_obligation_error(accounts, entry, JOB, 10_800, "h") is None
    err = _escrow_v23_sweep_obligation_error(accounts, entry, JOB, 10_801, "h")
    assert err is not None and "exceeds sweepable 10800" in err


def test_pure_path_fails_closed_without_the_allowance_in_context(rich):
    escrow = _settle_live_shape(rich)
    accounts = {escrow: rich.get(Account, (CHAIN, escrow))}
    ctx = {"remaining_obligation": 9_000, "obligation_unbounded": False, "escrow_addr": _escrow_address(JOB)}
    err = _escrow_v23_sweep_obligation_error(accounts, ctx, JOB, 1, "h")
    assert err is not None and "missing context" in err


def test_context_unsettled_job_carries_zero_allowance(rich, monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v23_height", 150)
    _fund_lock(rich, amount=LIVE_LOCK)
    ctx = build_escrow_context(rich, CHAIN, [_sweep_tx(amount=1)], block_height=200)
    assert ctx is not None and ctx[JOB]["fee_allowance"] == 0


def test_release_and_refund_bounds_are_untouched(rich):
    """The allowance is a sweep concept only: a release still cannot exceed the
    remaining obligation."""
    _fund_lock(rich, amount=LIVE_LOCK)
    ok, msg = _validate(rich, _release_tx(amount=LIVE_LOCK + 1), "rel-over")
    assert not ok
    assert "exceeds remaining obligation" in msg


# ---------------------------------------------------------------------------
# Seeded state-machine property test (the in-process counterpart of the
# aitbc-fuzz escrow fuzzer): random lock/release/refund/tip/sweep sequences
# through the REAL validate/apply code, compared against an independent model
# of the ruled bound, with the conservation invariants checked after every op.
# ---------------------------------------------------------------------------


def _model_ceiling(custody: int, locked: int, settled: int, swept: int, cap_bps: int) -> int:
    allowance = max(0, locked * cap_bps // 10_000 - swept) if settled > 0 else 0
    return custody - max(0, (locked - settled) - allowance)


def _run_sequence(session, seed: int, cap_bps: int) -> dict[str, int]:
    rng = random.Random(seed)
    job = f"job-prop-{seed}"
    # Independent sequences share one session: restart the signers' nonces.
    for addr in (AUTHORITY, BUYER):
        session.get(Account, (CHAIN, addr)).nonce = 0
    session.get(Account, (CHAIN, BUYER)).balance = 100_000_000
    session.commit()
    locked = rng.choice([1_000, 60_000, 152_434, 360_000, 1_800_000])
    escrow = _fund_lock(session, job_id=job, amount=locked)
    custody, settled, swept, tipped = locked, 0, 0, 0
    counts = {"ok": 0, "refused": 0}
    nonce = 0
    for step in range(rng.randint(3, 9)):
        op = rng.choice(["release", "refund", "tip", "sweep", "sweep", "release"])
        if op == "tip":
            amount = rng.randint(1, max(1, locked // 50))
            session.get(Account, (CHAIN, escrow)).balance += amount
            session.commit()
            custody += amount
            tipped += amount
            continue
        remaining = locked - settled
        if op == "sweep":
            ceiling = _model_ceiling(custody, locked, settled, swept, cap_bps)
            value = rng.choice([ceiling, ceiling + 1, ceiling - 1, rng.randint(1, max(1, custody)), 1])
            value = max(0, value)
            expect_ok = 0 < value <= custody and value <= ceiling
            tx = _sweep_tx(job_id=job, amount=value, nonce=nonce)
        else:
            bound = min(remaining, custody)
            value = rng.choice([bound, bound + 1, max(1, bound - rng.randint(0, max(0, bound))), rng.randint(1, locked)])
            value = max(0, value)
            expect_ok = 0 < value <= remaining and value <= custody
            if op == "release":
                tx = _release_tx(job_id=job, amount=value, nonce=nonce)
            else:
                tx = _refund_tx(job_id=job, amount=value, nonce=nonce)
        if value <= 0:
            continue
        h = f"{job}-{step}"
        ok, msg = _validate(session, tx, h)
        assert ok == expect_ok, (seed, step, op, value, custody, settled, swept, msg)
        if not ok:
            counts["refused"] += 1
            continue
        ok, msg = _apply(session, tx, h)
        assert ok, (seed, step, op, msg)
        _record(session, tx, h, block_height=200)
        nonce += 1
        counts["ok"] += 1
        custody -= value
        if op == "sweep":
            swept += value
        else:
            settled += value
        # Invariants after every accepted op.
        assert _balance(session, escrow) == custody >= 0, (seed, step)
        assert settled <= locked, ("I1 over-settlement", seed, step)
        # Sweeps may take only tips (residue) plus at most the governed cap of the lock.
        assert swept <= tipped + locked * cap_bps // 10_000, ("I8 sweep beyond residue+cap", seed, step, swept)
    return counts


@pytest.mark.parametrize("cap_bps", [300, 100, 0])
def test_random_sequences_match_the_model_and_hold_the_invariants(rich, cap_bps):
    if cap_bps != 300:
        _set(rich, "escrow_fee_cap_bps", str(cap_bps))
    n = int(os.environ.get("FEE_ALLOWANCE_PROP_SEEDS", "60"))
    base = int(os.environ.get("FEE_ALLOWANCE_PROP_BASE", "0"))
    ok = refused = 0
    for seed in range(base, base + n):
        counts = _run_sequence(rich, seed, cap_bps)
        ok += counts["ok"]
        refused += counts["refused"]
    # Both verdicts must be exercised or the test proves nothing.
    assert ok > n
    assert refused > 0
