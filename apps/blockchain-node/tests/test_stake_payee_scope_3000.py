"""#3000 (S01-STAKE-RELEASE-PAYEE-1): stake lock claims must be owner-scoped.

``Stake.id`` is a per-node sqlite PK, so the ``stake_id`` payload label on
``STAKE_LOCK``/``STAKE_RELEASE`` transactions is NOT globally unique — two
stakers on different nodes both have stake "5". Live proof: node0's stake 5
(``0x08aB…``) and the hub's stake 5 (``0xBdDF…``) collided, and the hub's
unstake claimed BOTH locks in ``lock_tx_hashes``. Consensus
``_load_claimed_locks`` requires every claimed lock's sender to be the
payee, so the release was rejected at block time after the row had already
flipped ``withdrawn`` — a stranded stake.

The fix scopes every bare-``stake_id`` lookup to the stake owner's address:

- ``_withdrawable_stake`` filters confirmed STAKE_LOCKs to ``sender ==
  stake.address`` before building ``lock_tx_hashes`` (top-up locks share
  sender + stake_id and stay claimed), so ``_assert_v4_maturity`` and the
  hash list see own locks only.
- ``_stake_release_state`` scopes the sealed STAKE_RELEASE lookup by
  ``recipient`` (the payee — sender is always the keyless escrow) and the
  pending check by the envelope's ``to``.
- ``block_deltas._orphan_target``/``_revive_confirmed_domain_rows`` apply
  the same owner scope for ``Stake`` rows.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import HTTPException
from sqlmodel import Session, create_engine
from sqlmodel.pool import StaticPool

from aitbc_chain.base_models import Block, Stake, Transaction, _to_ait_address
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.mempool_common import MempoolEntry
from aitbc_chain.models import Account
from aitbc_chain.rpc import staking

CHAIN = "test"  # whitelisted by the conftest _allow_test_chain_ids fixture

USER_KEY = keys.PrivateKey(b"\x11" * 32)
USER = USER_KEY.public_key.to_checksum_address()
FOREIGN_KEY = keys.PrivateKey(b"\x22" * 32)
FOREIGN = FOREIGN_KEY.public_key.to_checksum_address()

# The live collision: both nodes hold a local stake whose sqlite id is 5.
STAKE_ID = 5


def _sign(message: dict[str, Any], key: keys.PrivateKey) -> str:
    digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())
    return key.sign_msg_hash(digest).to_hex()


def _unstake_body(stake_id: Any, *, nonce: int = 0) -> dict[str, Any]:
    """A fully-signed unstake request — mirrors _signed_stake_body."""
    message = {
        "address": USER.lower(),
        "chain_id": CHAIN,
        "action": "unstake",
        "nonce": nonce,
        "timestamp": time.time(),
        "stake_id": stake_id,
    }
    return {
        **message,
        "address": USER,
        "signature": _sign(message, USER_KEY),
    }


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def rpc_db(engine, monkeypatch):
    """Route staking.session_scope at the test engine, arm v17, and stub
    the mempool queue so no real transaction is emitted."""

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(staking, "session_scope", _session_scope)
    monkeypatch.setattr(settings, "state_transition_v17_height", 1)
    queued: list[dict[str, Any]] = []

    def _fake_queue(**kwargs):
        queued.append(kwargs)
        return "0x" + "ab" * 32

    monkeypatch.setattr(staking, "queue_protocol_transfer", _fake_queue)
    return engine, queued, monkeypatch


def _seed_account(engine, balance: int = 10**9, nonce: int = 0) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=_to_ait_address(USER), balance=balance, nonce=nonce))
        session.commit()


def _seed_stake(engine, *, stake_id: int = STAKE_ID, status: str = "active", amount: int = 1000) -> int:
    """A matured stake row with an explicit sqlite id (the collision key)."""
    with Session(engine) as session:
        stake = Stake(
            id=stake_id,
            chain_id=CHAIN,
            address=USER,
            amount=amount,
            locked_until=datetime.now(UTC) - timedelta(days=1),
            status=status,
        )
        session.add(stake)
        session.commit()
        return stake_id


def _add_lock_tx(
    session: Session,
    *,
    label: str,
    sender: str,
    stake_id_payload: Any = STAKE_ID,
    value: int = 1000,
    block_height: int = 1,
    extra_payload: dict[str, Any] | None = None,
) -> str:
    """Insert a sealed STAKE_LOCK Transaction; returns its tx_hash."""
    tx_hash = "0x" + keccak(f"{label}-{sender}-{stake_id_payload}".encode()).hex()[:64]
    payload: dict[str, Any] = {"stake_id": str(stake_id_payload)}
    if extra_payload:
        payload.update(extra_payload)
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            block_height=block_height,
            sender=_to_ait_address(sender),
            recipient=staking.stake_escrow_address(),
            value=value,
            type="STAKE_LOCK",
            payload=payload,
        )
    )
    session.commit()
    return tx_hash


def _add_release_tx(
    session: Session,
    *,
    label: str,
    recipient: str,
    stake_id_payload: Any = STAKE_ID,
    sender: str | None = None,
    block_height: int = 2,
) -> str:
    """Insert a sealed STAKE_RELEASE Transaction; returns its tx_hash."""
    tx_hash = "0x" + keccak(f"release-{label}-{recipient}-{stake_id_payload}".encode()).hex()[:64]
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=tx_hash,
            block_height=block_height,
            sender=_to_ait_address(sender or staking.stake_escrow_address()),
            recipient=_to_ait_address(recipient),
            value=1000,
            type="STAKE_RELEASE",
            payload={"stake_id": str(stake_id_payload)},
        )
    )
    session.commit()
    return tx_hash


def _add_pending_release(session: Session, *, label: str, to: str | None, stake_id_payload: Any = STAKE_ID) -> None:
    content: dict[str, Any] = {
        "type": "STAKE_RELEASE",
        "from": staking.stake_escrow_address(),
        "payload": {"stake_id": str(stake_id_payload)},
    }
    if to is not None:
        content["to"] = _to_ait_address(to)
    session.add(
        MempoolEntry(
            chain_id=CHAIN,
            tx_hash="0x" + keccak(f"pending-{label}".encode()).hex()[:64],
            content=json.dumps(content),
            fee=0,
            size_bytes=1,
            received_at=1.0,
        )
    )
    session.commit()


def _stake_row(engine, stake_id: int) -> Stake:
    with Session(engine) as session:
        return session.get(Stake, stake_id)


def _release_hashes(queued: list[dict[str, Any]]) -> list[str]:
    release = next(q for q in queued if q["tx_type"] == "STAKE_RELEASE")
    return list(release["payload"]["lock_tx_hashes"])


@pytest.mark.asyncio
async def test_unstake_claims_only_own_sender_locks_under_colliding_stake_id(rpc_db):
    """The live repro: a foreign staker's STAKE_LOCK carrying the same
    ``stake_id`` must not land in this release's ``lock_tx_hashes`` — that
    is exactly what consensus rejected on the fleet."""
    engine, queued, _monkeypatch = rpc_db
    _seed_account(engine)
    _seed_stake(engine)
    with Session(engine) as session:
        own_hash = _add_lock_tx(session, label="own", sender=USER)
        _add_lock_tx(session, label="foreign", sender=FOREIGN)
    queued.clear()

    result = staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(STAKE_ID))

    assert result["success"] is True
    assert _release_hashes(queued) == [own_hash]
    assert _stake_row(engine, STAKE_ID).status == "withdrawn"


@pytest.mark.asyncio
async def test_unstake_claims_all_own_locks_including_topups(rpc_db):
    """Top-up locks share the owner's sender and stake_id — every one of
    them stays claimed alongside the foreign lock being excluded."""
    engine, queued, _monkeypatch = rpc_db
    _seed_account(engine)
    _seed_stake(engine, amount=3000)
    with Session(engine) as session:
        first = _add_lock_tx(session, label="own-1", sender=USER, value=1000)
        second = _add_lock_tx(session, label="own-2", sender=USER, value=2000)
        _add_lock_tx(session, label="foreign", sender=FOREIGN, value=5000)
        _add_lock_tx(session, label="foreign-2", sender=FOREIGN, value=7000)
    queued.clear()

    result = staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(STAKE_ID))

    assert result["success"] is True
    assert sorted(_release_hashes(queued)) == sorted([first, second])


@pytest.mark.asyncio
async def test_foreign_unmatured_lock_does_not_block_v4_maturity(rpc_db):
    """``_assert_v4_maturity`` must evaluate own locks only: an immature
    foreign lock under the same stake_id would 400 the release if it were
    still in the claim set."""
    engine, queued, monkeypatch = rpc_db
    monkeypatch.setattr(settings, "state_transition_v4_height", 1)
    _seed_account(engine)
    _seed_stake(engine)
    with Session(engine) as session:
        session.add(
            Block(chain_id=CHAIN, height=10, hash="0x" + "10" * 32, parent_hash="0x" + "0f" * 32, proposer="0x" + "0" * 40)
        )
        session.commit()
        # Own lock carries no lock_days → matured by definition.
        _add_lock_tx(session, label="own", sender=USER, block_height=9)
        # Foreign lock with a far-future v4 window — fatal if unfiltered.
        _add_lock_tx(
            session,
            label="foreign",
            sender=FOREIGN,
            block_height=10,
            extra_payload={"lock_days": 3650},
        )
    queued.clear()

    result = staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(STAKE_ID))

    assert result["success"] is True
    assert len(_release_hashes(queued)) == 1


@pytest.mark.asyncio
async def test_unstake_with_only_foreign_locks_is_not_yet_confirmed(rpc_db):
    """Filtering can empty the claim set: when every STAKE_LOCK under this
    stake_id belongs to a foreign sender, the own lock genuinely has not
    confirmed — the same 409 the unfiltered path raises applies."""
    engine, queued, _monkeypatch = rpc_db
    _seed_account(engine)
    _seed_stake(engine)
    with Session(engine) as session:
        _add_lock_tx(session, label="foreign", sender=FOREIGN)
    queued.clear()

    with pytest.raises(HTTPException) as exc:
        staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(STAKE_ID))
    assert exc.value.status_code == 409
    assert "not yet confirmed" in exc.value.detail
    assert _stake_row(engine, STAKE_ID).status == "active"
    assert not [q for q in queued if q["tx_type"] == "STAKE_RELEASE"]


def test_stake_release_state_ignores_foreign_sealed_release(engine):
    """A foreign payee's sealed STAKE_RELEASE under the same stake_id must
    not report ``sealed`` (or heal) for this stake."""
    _seed_stake(engine)
    with Session(engine) as session:
        _add_release_tx(session, label="foreign", recipient=FOREIGN)
        assert staking._stake_release_state(session, CHAIN, STAKE_ID, _to_ait_address(USER)) is None

        _add_release_tx(session, label="own", recipient=USER)
        assert staking._stake_release_state(session, CHAIN, STAKE_ID, _to_ait_address(USER)) == "sealed"


def test_stake_release_state_ignores_foreign_pending_release(engine):
    """Same scoping on the mempool side via the envelope's ``to`` field."""
    _seed_stake(engine)
    with Session(engine) as session:
        _add_pending_release(session, label="foreign", to=FOREIGN)
        assert staking._stake_release_state(session, CHAIN, STAKE_ID, _to_ait_address(USER)) is None

        _add_pending_release(session, label="own", to=USER)
        assert staking._stake_release_state(session, CHAIN, STAKE_ID, _to_ait_address(USER)) == "pending"


def test_stake_release_state_pending_without_to_still_counts(engine):
    """Fail-safe direction: an envelope that does not carry ``to`` cannot
    disprove ownership, so it still counts as pending rather than risking
    a double release."""
    _seed_stake(engine)
    with Session(engine) as session:
        _add_pending_release(session, label="no-to", to=None)
        assert staking._stake_release_state(session, CHAIN, STAKE_ID, _to_ait_address(USER)) == "pending"


@pytest.mark.asyncio
async def test_unstake_withdrawn_retryable_despite_foreign_sealed_release(rpc_db):
    """The #2629 retry path must not be poisoned by a foreign release: a
    ``withdrawn`` stake whose only STAKE_RELEASE belongs to another
    payee is still owed its own release."""
    engine, queued, _monkeypatch = rpc_db
    _seed_account(engine)
    _seed_stake(engine, status="withdrawn")
    with Session(engine) as session:
        _add_lock_tx(session, label="own", sender=USER)
        _add_release_tx(session, label="foreign", recipient=FOREIGN)
    queued.clear()

    result = staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(STAKE_ID))

    assert result["success"] is True
    assert result["status"] == "withdrawn"
    assert any(q["tx_type"] == "STAKE_RELEASE" for q in queued)


@pytest.mark.asyncio
async def test_unstake_active_with_foreign_sealed_release_does_not_heal(rpc_db):
    """An active stake must not be flipped ``withdrawn`` by a foreign
    payee's sealed release under a colliding stake_id — the old code
    healed the row and 409'd, stranding the real principal."""
    engine, queued, _monkeypatch = rpc_db
    _seed_account(engine)
    _seed_stake(engine)  # status stays "active"
    with Session(engine) as session:
        own_hash = _add_lock_tx(session, label="own", sender=USER)
        _add_release_tx(session, label="foreign", recipient=FOREIGN)
    queued.clear()

    result = staking.unstake_tokens(request=Mock(), unstake_data=_unstake_body(STAKE_ID))

    assert result["success"] is True
    assert _release_hashes(queued) == [own_hash]
    assert _stake_row(engine, STAKE_ID).status == "withdrawn"
