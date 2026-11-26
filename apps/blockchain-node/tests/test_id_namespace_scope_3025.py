"""#3025 ESCROW-BAOUNTY-AGENTSTAKE-ID-COLLISION-1 — owner-scoped id claims.

``bounty_id`` and ``agent_stake_id`` are caller-chosen strings whose
uniqueness constraint is per-node sqlite, not per-chain — two operators on
different nodes can hold different records under the same id on one chain
(the #3000 ``stake_id`` genus on two more namespaces). Every bare payload
match therefore also returns *foreign* locks/markers:

- ``_require_funded``/``_heal_missing_outflow`` merged a foreign creator's
  BOUNTY_LOCKs into this bounty's funded total — an unfunded bounty could
  pay out of a sibling's escrow, or a heal could pay the merged sum.
- ``complete_agent_stake`` claimed ALL matching STAKE_LOCKs into
  ``lock_tx_hashes``; consensus requires every claimed lock's sender to be
  the payee, so a foreign staker's lock got the release apply-rejected
  after the row flipped — or, same staker on two nodes, the first release
  spent every lock and the sibling record stranded.
- ``_canonical_status``/``_agent_lock_in_flight``/``_reconcile_agent_topup``
  and the pending probes matched bare ids the same way.
- ``block_deltas`` orphan-mark/revive scoped ``Stake`` only (#3000);
  ``AgentStakeRecord``/``BountyContract`` rows had no owner scope.

The fix scopes every claim set by the envelope party that identifies the
owner: locks by ``sender`` (creator/staker), releases by ``recipient``
(the payee — sender is always the keyless escrow), pending mempool probes
by the same ``from``/``to`` fields. STAKE_UNBOND is an escrow→escrow
self-marker with no owner field and stays unscoped (documented residual —
it can only flip the unbonding transition, which unbond/complete still
gate on ``staker_address`` + maturity).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from aitbc_chain.base_models import (
    AgentStakeRecord,
    BountyContract,
    BountySubmissionRecord,
    Transaction,
    _to_ait_address,
)
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.mempool_common import MempoolEntry
from aitbc_chain.models import Account
from aitbc_chain.rpc import agent_staking, bounty
from aitbc_chain.state import block_deltas

CHAIN = "test"

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
FOREIGN_KEY = keys.PrivateKey(b"\x22" * 32)
FOREIGN = FOREIGN_KEY.public_key.to_checksum_address()
WINNER_KEY = keys.PrivateKey(b"\x44" * 32)
WINNER = WINNER_KEY.public_key.to_checksum_address()
OP_KEY = keys.PrivateKey(b"\x33" * 32)
OP_ADDR = OP_KEY.public_key.to_checksum_address()

SID = "stake-collision-1"
BID = "bounty-collision-1"
AMOUNT = 1000


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _signed_body(fields: dict[str, Any]) -> dict[str, Any]:
    return {**fields, "signature": _sign(fields, OP_KEY)}


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def rpc_db(engine, monkeypatch):
    """session_scope on the test engine for both routers, armed transfers,
    and a queue_protocol_transfer spy per module."""
    monkeypatch.setenv("AGENT_ECONOMICS_OPERATOR_ADDRESS", OP_ADDR)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    @contextmanager
    def _session_scope(*args, **kwargs):
        with factory() as session:
            yield session

    for module in (agent_staking, bounty):
        monkeypatch.setattr(module, "session_scope", _session_scope)
        monkeypatch.setattr(module, "protocol_transfers_active", lambda *a, **k: True)
        queued: list[dict[str, Any]] = []

        def _make_queue(q: list[dict[str, Any]]):
            def _queue(**kwargs):
                q.append(kwargs)
                return "0x" + "ab" * 32

            return _queue

        monkeypatch.setattr(module, "queue_protocol_transfer", _make_queue(queued))
        module._queued = queued
    return engine


def _seed_account(engine, address: str = USER, balance: int = 10**9) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=_to_ait_address(address), balance=balance))
        session.commit()


def _tx(
    *,
    label: str,
    tx_type: str,
    sender: str,
    recipient: str,
    payload: dict[str, Any],
    value: int = 0,
    height: int = 1,
) -> str:
    tx_hash = "0x" + keccak(f"{label}-{sender}-{tx_type}".encode()).hex()[:64]
    return tx_hash, Transaction(
        chain_id=CHAIN,
        tx_hash=tx_hash,
        block_height=height,
        sender=_to_ait_address(sender),
        recipient=_to_ait_address(recipient),
        value=value,
        type=tx_type,
        payload=payload,
    )


def _seed_tx(engine, **kwargs) -> str:
    tx_hash, tx = _tx(**kwargs)
    with Session(engine) as session:
        session.add(tx)
        session.commit()
    return tx_hash


def _seed_agent_stake(engine, *, status: str = "unbonding", staker: str = USER, amount: int = AMOUNT) -> None:
    with Session(engine) as session:
        session.add(
            AgentStakeRecord(
                chain_id=CHAIN,
                stake_id=SID,
                staker_address=_to_ait_address(staker),
                agent_wallet=_to_ait_address(staker),
                amount=amount,
                lock_period=30,
                locked_until=datetime.now(UTC) - timedelta(days=1),
                status=status,
            )
        )
        session.commit()


def _seed_bounty(engine, *, status: str = "active", creator: str = USER, reward: int = 100) -> None:
    with Session(engine) as session:
        session.add(
            BountyContract(
                chain_id=CHAIN,
                bounty_id=BID,
                creator_address=_to_ait_address(creator),
                reward_amount=reward,
                remaining_amount=reward,
                status=status,
                winner_address=_to_ait_address(WINNER) if status == "completed" else None,
            )
        )
        session.commit()


def _seed_submission(engine, *, status: str = "verified") -> None:
    with Session(engine) as session:
        session.add(
            BountySubmissionRecord(
                chain_id=CHAIN,
                bounty_id=BID,
                submission_id="sub-1",
                submitter_address=_to_ait_address(WINNER),
                status=status,
            )
        )
        session.commit()


def _complete_body() -> dict[str, Any]:
    return _signed_body({"stake_id": SID, "user_address": USER, "chain_id": CHAIN})


# --------------------------------------------------------------------------- #
# agent_stake: complete claims only own locks (the freeze/theft path)
# --------------------------------------------------------------------------- #


def test_complete_release_claims_only_own_locks(engine, rpc_db):
    """Foreign staker's STAKE_LOCK under the same agent_stake_id must not
    land in lock_tx_hashes — consensus would reject the release (sender !=
    payee) after the row flipped."""
    _seed_account(engine)
    _seed_agent_stake(engine)
    own_hash = _seed_tx(
        engine,
        label="own-lock",
        tx_type="STAKE_LOCK",
        sender=USER,
        recipient=agent_staking.stake_escrow_address(),
        payload={"agent_stake_id": SID},
        value=AMOUNT,
    )
    _seed_tx(
        engine,
        label="foreign-lock",
        tx_type="STAKE_LOCK",
        sender=FOREIGN,
        recipient=agent_staking.stake_escrow_address(),
        payload={"agent_stake_id": SID},
        value=9000,
    )

    result = agent_staking.complete_agent_stake(Mock(), SID, _complete_body())

    assert result["status"] == "completed"
    release = next(q for q in agent_staking._queued if q["tx_type"] == "STAKE_RELEASE")  # type: ignore[attr-defined]
    assert release["payload"]["lock_tx_hashes"] == [own_hash]


def test_complete_still_409s_when_only_foreign_lock_backs_it(engine, rpc_db):
    """A foreign lock must not satisfy this stake's funding check either."""
    _seed_account(engine)
    _seed_agent_stake(engine)
    _seed_tx(
        engine,
        label="foreign-lock-only",
        tx_type="STAKE_LOCK",
        sender=FOREIGN,
        recipient=agent_staking.stake_escrow_address(),
        payload={"agent_stake_id": SID},
        value=AMOUNT,
    )

    with pytest.raises(HTTPException) as exc:
        agent_staking.complete_agent_stake(Mock(), SID, _complete_body())
    assert exc.value.status_code == 409


def test_topup_reconcile_ignores_foreign_locks(engine, rpc_db):
    """``_reconcile_agent_topup`` counted foreign locks toward ``accounted``
    — a colliding top-up could 409 an honest retry or consolidate onto a
    foreign lock."""
    _seed_agent_stake(engine, status="active")
    _seed_tx(
        engine,
        label="foreign-topup",
        tx_type="STAKE_LOCK",
        sender=FOREIGN,
        recipient=agent_staking.stake_escrow_address(),
        payload={"agent_stake_id": SID, "additional_amount": 500},
        value=500,
    )
    with Session(engine) as session:
        record = session.exec(select(AgentStakeRecord).where(AgentStakeRecord.stake_id == SID)).one()
        # Before the fix this raised 409 (accounted=500 vs amount=1000) or
        # returned an early dict; scoped, no foreign lock matches → None.
        assert agent_staking._reconcile_agent_topup(session, CHAIN, record, 500, SID) is None


def test_canonical_status_scoped_by_owner(engine):
    """A foreign staker's sealed STAKE_RELEASE under a colliding id must
    not report this stake completed; unscoped reads keep #719 semantics."""
    _seed_tx(
        engine,
        label="foreign-release",
        tx_type="STAKE_RELEASE",
        sender=agent_staking.stake_escrow_address(),
        recipient=FOREIGN,
        payload={"agent_stake_id": SID},
        value=AMOUNT,
    )
    with Session(engine) as session:
        assert agent_staking._canonical_status(session, CHAIN, SID, owner=USER) == (None, "none")
        # Documented: owner-less reads (public status endpoint) stay bare.
        assert agent_staking._canonical_status(session, CHAIN, SID) == ("completed", "chain")


def test_agent_lock_in_flight_scoped_sealed_and_pending(engine):
    _seed_tx(
        engine,
        label="foreign-lock",
        tx_type="STAKE_LOCK",
        sender=FOREIGN,
        recipient=agent_staking.stake_escrow_address(),
        payload={"agent_stake_id": SID},
        value=AMOUNT,
    )
    with Session(engine) as session:
        session.add(
            MempoolEntry(
                chain_id=CHAIN,
                tx_hash="0x" + keccak(b"pending-foreign").hex()[:64],
                content=json.dumps(
                    {
                        "type": "STAKE_LOCK",
                        "from": _to_ait_address(FOREIGN),
                        "payload": {"agent_stake_id": SID},
                    }
                ),
                fee=0,
                size_bytes=1,
                received_at=1.0,
            )
        )
        session.commit()
        assert agent_staking._agent_lock_in_flight(session, CHAIN, SID, USER) is None
        assert agent_staking._agent_lock_in_flight(session, CHAIN, SID, FOREIGN) == "sealed"


# --------------------------------------------------------------------------- #
# bounty: funded total and heal amount are creator-scoped
# --------------------------------------------------------------------------- #


def _deploy_body(bounty_id: str = BID, amount: int = 100) -> dict[str, Any]:
    return _signed_body({"bounty_id": bounty_id, "user_address": USER, "reward_amount": amount, "chain_id": CHAIN})


def test_verify_409s_when_only_a_foreign_lock_backs_the_id(engine, rpc_db):
    """The audit repro: node B's colliding bounty must not see node A's
    lock as its funding — unfunded verify refuses instead of paying."""
    _seed_account(engine)
    bounty.deploy_bounty(Mock(), _deploy_body())
    _seed_tx(
        engine,
        label="foreign-bounty-lock",
        tx_type="BOUNTY_LOCK",
        sender=FOREIGN,
        recipient=bounty.bounty_escrow_address(),
        payload={"bounty_id": BID},
        value=500,
    )
    bounty.submit_bounty(
        Mock(),
        BID,
        _signed_body({"bounty_id": BID, "submission_id": "sub-1", "user_address": WINNER, "chain_id": CHAIN}),
    )
    with pytest.raises(HTTPException) as exc:
        bounty.verify_bounty(
            Mock(),
            BID,
            _signed_body({"bounty_id": BID, "submission_id": "sub-1", "verified": True, "chain_id": CHAIN}),
        )
    assert exc.value.status_code == 409


def test_heal_payout_amount_excludes_foreign_locks(engine, rpc_db):
    """``_heal_missing_outflow`` paid ``confirmed_lock_total`` — the MERGED
    sum across colliding bounty_ids — to one winner, draining the sibling's
    principal. Scoped, the heal pays only this creator's locks."""
    _seed_account(engine)
    bounty.deploy_bounty(Mock(), _deploy_body())
    # Completed bounty whose payout never queued (the #2637 heal path).
    with Session(engine) as session:
        row = session.exec(select(BountyContract).where(BountyContract.bounty_id == BID)).one()
        row.status = "completed"
        row.winner_address = _to_ait_address(WINNER)
        row.remaining_amount = 100
        session.add(row)
        session.commit()
    _seed_submission(engine, status="verified")
    _seed_tx(
        engine,
        label="own-bounty-lock",
        tx_type="BOUNTY_LOCK",
        sender=USER,
        recipient=bounty.bounty_escrow_address(),
        payload={"bounty_id": BID},
        value=100,
    )
    _seed_tx(
        engine,
        label="foreign-bounty-lock",
        tx_type="BOUNTY_LOCK",
        sender=FOREIGN,
        recipient=bounty.bounty_escrow_address(),
        payload={"bounty_id": BID},
        value=500,
    )

    result = bounty.verify_bounty(
        Mock(),
        BID,
        _signed_body({"bounty_id": BID, "submission_id": "sub-1", "verified": True, "chain_id": CHAIN}),
    )

    assert result["idempotent"] is True
    payout = next(q for q in bounty._queued if q["tx_type"] == "BOUNTY_PAYOUT")  # type: ignore[attr-defined]
    assert payout["amount"] == 100  # own lock only — not the merged 600


def test_foreign_payout_does_not_suppress_own_heal(engine, rpc_db):
    """A foreign creator's sealed BOUNTY_PAYOUT under the same bounty_id
    used to satisfy ``_bounty_flow_tx_exists`` and skip this bounty's heal,
    stranding its lock. Scoped by recipient it cannot."""
    _seed_account(engine)
    bounty.deploy_bounty(Mock(), _deploy_body())
    with Session(engine) as session:
        row = session.exec(select(BountyContract).where(BountyContract.bounty_id == BID)).one()
        row.status = "expired"
        row.remaining_amount = 0
        session.add(row)
        session.commit()
    _seed_tx(
        engine,
        label="foreign-refund",
        tx_type="BOUNTY_REFUND",
        sender=bounty.bounty_escrow_address(),
        recipient=FOREIGN,
        payload={"bounty_id": BID},
        value=500,
    )
    # This bounty has no own outflow and no confirmed lock — heal must at
    # least *attempt* (it bails on amount<=0), proving the existence check
    # no longer short-circuits on the foreign refund. Give it an own lock
    # so the heal actually queues.
    _seed_tx(
        engine,
        label="own-bounty-lock-2",
        tx_type="BOUNTY_LOCK",
        sender=USER,
        recipient=bounty.bounty_escrow_address(),
        payload={"bounty_id": BID},
        value=100,
    )

    result = bounty.expire_bounty(Mock(), BID, _signed_body({"bounty_id": BID, "user_address": USER, "chain_id": CHAIN}))

    assert result["idempotent"] is True
    refund = next(q for q in bounty._queued if q["tx_type"] == "BOUNTY_REFUND")  # type: ignore[attr-defined]
    assert refund["amount"] == 100
    assert refund["recipient"] == _to_ait_address(USER)


# --------------------------------------------------------------------------- #
# block_deltas: orphan-mark / revive owner scope extended to the new
# namespaces (#3000 covered Stake only)
# --------------------------------------------------------------------------- #


def _orphan_session(engine):
    return Session(engine)


def test_orphan_target_ignores_foreign_lost_lock_for_agent_stake(engine):
    """Node B's lost STAKE_LOCK under a colliding agent_stake_id must not
    orphan-mark node A's row — and node A's own lost lock must not be
    "backed" by B's confirmed foreign lock."""
    _seed_agent_stake(engine, status="active")
    _seed_tx(
        engine,
        label="foreign-confirmed-lock",
        tx_type="STAKE_LOCK",
        sender=FOREIGN,
        recipient=agent_staking.stake_escrow_address(),
        payload={"agent_stake_id": SID},
        value=AMOUNT,
    )
    with _orphan_session(engine) as session:
        record = session.exec(select(AgentStakeRecord).where(AgentStakeRecord.stake_id == SID)).one()
        # B's lock lost in a fork: not A's row to orphan.
        assert not block_deltas._orphan_target(
            session,
            CHAIN,
            "STAKE_LOCK",
            {"from": FOREIGN, "tx_hash": "0xf1"},
            AgentStakeRecord,
            "stake_id",
            "agent_stake_id",
            SID,
        )
        assert record.status == "active"
        # A's lock lost while only B's confirmed lock remains: orphan it —
        # the foreign confirmed lock must not stand in for A's own.
        assert block_deltas._orphan_target(
            session,
            CHAIN,
            "STAKE_LOCK",
            {"from": USER, "tx_hash": "0xf2"},
            AgentStakeRecord,
            "stake_id",
            "agent_stake_id",
            SID,
        )
        session.commit()
    with Session(engine) as session:
        assert session.exec(select(AgentStakeRecord).where(AgentStakeRecord.stake_id == SID)).one().status == "orphaned"


def test_orphan_target_ignores_foreign_lost_lock_for_bounty(engine):
    _seed_bounty(engine)
    _seed_tx(
        engine,
        label="foreign-bounty-lock-3",
        tx_type="BOUNTY_LOCK",
        sender=FOREIGN,
        recipient=bounty.bounty_escrow_address(),
        payload={"bounty_id": BID},
        value=100,
    )
    with _orphan_session(engine) as session:
        assert not block_deltas._orphan_target(
            session, CHAIN, "BOUNTY_LOCK", {"from": FOREIGN, "tx_hash": "0xb1"}, BountyContract, "bounty_id", "bounty_id", BID
        )
        # The creator's own lock lost while only the foreign confirmed lock
        # remains: orphan it — the foreign lock must not stand in.
        assert block_deltas._orphan_target(
            session, CHAIN, "BOUNTY_LOCK", {"from": USER, "tx_hash": "0xb2"}, BountyContract, "bounty_id", "bounty_id", BID
        )
        session.commit()
    with Session(engine) as session:
        assert session.exec(select(BountyContract).where(BountyContract.bounty_id == BID)).one().status == "orphaned"


def test_revive_confirmed_domain_rows_scoped_to_owner(engine):
    """An orphaned agent_stake row must revive only on *its own* confirmed
    lock — a foreign staker's lock under the colliding id cannot."""
    _seed_agent_stake(engine, status="orphaned")
    _seed_tx(
        engine,
        label="foreign-lock-revive",
        tx_type="STAKE_LOCK",
        sender=FOREIGN,
        recipient=agent_staking.stake_escrow_address(),
        payload={"agent_stake_id": SID},
        value=AMOUNT,
    )

    revived = block_deltas._revive_confirmed_domain_rows(lambda: Session(engine), CHAIN)
    assert revived == 0
    with Session(engine) as session:
        assert session.exec(select(AgentStakeRecord).where(AgentStakeRecord.stake_id == SID)).one().status == "orphaned"

    _seed_tx(
        engine,
        label="own-lock-revive",
        tx_type="STAKE_LOCK",
        sender=USER,
        recipient=agent_staking.stake_escrow_address(),
        payload={"agent_stake_id": SID},
        value=AMOUNT,
    )
    revived = block_deltas._revive_confirmed_domain_rows(lambda: Session(engine), CHAIN)
    assert revived == 1
    with Session(engine) as session:
        assert session.exec(select(AgentStakeRecord).where(AgentStakeRecord.stake_id == SID)).one().status == "active"
