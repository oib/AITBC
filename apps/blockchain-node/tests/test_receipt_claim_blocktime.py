"""#844: every RECEIPT_CLAIM branch stamps the sealed block time, not wall-clock.

The minted-amount branch in both apply paths used ``datetime.now(UTC)`` where
its siblings already stamped ``block_time`` at v18+ — two nodes applying the
same block wrote different ``claimed_at`` values. Each branch below is applied
twice under two different frozen wall-clocks; ``claimed_at`` must be the
sealed block time on every branch and both runs must agree exactly.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import Session, select

import aitbc_chain.state.pure_state_transition as pure_mod
import aitbc_chain.state.state_transition as seq_mod
from aitbc_chain.base_models import Account, Receipt
from aitbc_chain.state.pure_state_transition import apply_deltas_to_db, compute_state_delta
from aitbc_chain.state.state_transition import (
    StateTransition,
    _bridge_release_authority,
    build_bridge_lock_context,
    build_escrow_context,
)

from test_apply_parity import (
    CHAIN,
    HEIGHT,
    PROVIDER,
    PROVIDER_KEY,
    _attach_sender_sig,
    _hash,
    _new_engine,
    _prepare,
    _seed_common,
    _tx,
)

V = 18
BLOCK_TIME = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
WALL_A = datetime(2030, 1, 1, tzinfo=UTC)
WALL_B = datetime(2031, 6, 6, tzinfo=UTC)

RECEIPT_SEEDED = _hash("receipt", "claim844-seeded")
RECEIPT_NOMINT = _hash("receipt", "claim844-nomint")
RECEIPT_CARRIED = _hash("receipt", "claim844-carried")


def _freeze(monkeypatch, at: datetime) -> None:
    frozen = type("FrozenDT", (datetime,), {"now": classmethod(lambda cls, tz=None: at)})
    monkeypatch.setattr(seq_mod, "datetime", frozen)
    monkeypatch.setattr(pure_mod, "datetime", frozen)


def _seed_for(branch: str):
    def seed(s: Session) -> None:
        if branch == "minted":
            s.add(
                Receipt(
                    chain_id=CHAIN,
                    job_id="job-claim844-m",
                    receipt_id=RECEIPT_SEEDED,
                    payload={"units": 12},
                    miner_signature={"sig": "miner"},
                    coordinator_attestations=[{"att": "coord"}],
                    minted_amount=1234,
                    status="pending",
                )
            )
        elif branch == "nomint":
            s.add(
                Receipt(
                    chain_id=CHAIN,
                    job_id="job-claim844-n",
                    receipt_id=RECEIPT_NOMINT,
                    payload={"units": 7},
                    miner_signature={"sig": "miner"},
                    coordinator_attestations=[{"att": "coord"}],
                    minted_amount=None,
                    status="pending",
                )
            )

    return seed


def _claim_tx(branch: str) -> dict:
    if branch == "carried":
        payload = {
            "receipt_id": RECEIPT_CARRIED,
            "receipt": {
                "receipt_id": RECEIPT_CARRIED,
                "job_id": "job-claim844-c",
                "payload": {"units": 5},
                "miner_signature": {"sig": "miner"},
                "coordinator_attestations": [{"att": "coord"}],
            },
        }
    else:
        payload = {"receipt_id": RECEIPT_SEEDED if branch == "minted" else RECEIPT_NOMINT}
    tx = _tx(PROVIDER, PROVIDER, 0, "RECEIPT_CLAIM", payload)
    return _prepare(_attach_sender_sig(tx, PROVIDER_KEY), V)


def _claimed_at(engine, receipt_id: str):
    with Session(engine) as s:
        row = s.exec(select(Receipt).where(Receipt.chain_id == CHAIN, Receipt.receipt_id == receipt_id)).one()
        assert row.status == "claimed"
        return row.claimed_at


def _apply(tmp_path: Path, branch: str, path: str, wallclock: datetime, monkeypatch, tag: str):
    _freeze(monkeypatch, wallclock)
    eng = _new_engine(tmp_path, tag)
    tx = _claim_tx(branch)
    tx_hash = _hash("claim844", branch, path, tag)
    receipt_id = {
        "minted": RECEIPT_SEEDED,
        "nomint": RECEIPT_NOMINT,
        "carried": RECEIPT_CARRIED,
    }[branch]
    with Session(eng) as s:
        _seed_common(s)
        _seed_for(branch)(s)
        s.commit()
    if path == "sequential":
        with Session(eng) as s:
            ok, _msg = StateTransition().apply_transaction(
                s, CHAIN, tx, tx_hash, block_version=V, block_height=HEIGHT, block_time=BLOCK_TIME
            )
            assert ok, _msg
            s.commit()
    else:
        with Session(eng) as s:
            account_map = {
                a.address: Account(chain_id=a.chain_id, address=a.address, balance=a.balance, nonce=a.nonce)
                for a in s.exec(select(Account).where(Account.chain_id == CHAIN)).all()
            }
            delta = compute_state_delta(
                account_map,
                tx,
                CHAIN,
                tx_hash,
                set(),
                block_version=V,
                escrow_context=build_escrow_context(s, CHAIN, [tx], block_height=HEIGHT),
                bridge_authority=_bridge_release_authority(s, CHAIN, HEIGHT),
                bridge_lock_context=build_bridge_lock_context(s, CHAIN, [tx]),
            )
            assert delta.success, delta.error
            apply_deltas_to_db(s, [delta], CHAIN, block_version=V, block_height=HEIGHT, block_time=BLOCK_TIME)
            s.commit()
    got = _claimed_at(eng, receipt_id)
    eng.dispose()
    return got


@pytest.mark.parametrize("path", ("sequential", "pure"))
@pytest.mark.parametrize("branch", ("minted", "nomint", "carried"))
def test_claimed_at_is_the_sealed_block_time(tmp_path, monkeypatch, branch, path):
    a = _apply(tmp_path, branch, path, WALL_A, monkeypatch, f"{branch}-{path}-a")
    b = _apply(tmp_path, branch, path, WALL_B, monkeypatch, f"{branch}-{path}-b")
    assert a == b, "same block applied under two wall-clocks stamped different claimed_at"
    assert a == BLOCK_TIME.replace(tzinfo=None) or a == BLOCK_TIME
