"""V-1 close condition — replay every waived v9 type on a fixture chain.

Each transaction type listed in
``docs/decisions/v1-v9-live-exercise-waivers.md`` (the 22 types that have
never sealed since state-transition v9 activated at height 30400) gets one
parametrized case here. Per type the test:

1. seeds a fixture chain (funded actors, authority parameters, and the
   type's prerequisite chain state — a lock to release, a bond to slash,
   a pool to withdraw from, …),
2. applies a properly-signed transaction of that type through the real
   ``StateTransition.apply_transaction`` at ``block_version=9``,
3. applies the identical transaction a second time on a second,
   identically-seeded database — the replay must produce the identical
   verdict and the identical final state (account rows + full state
   root), which is the determinism property a sealed transaction proves.

Everything is deterministic: fixed fixture keys, fixed hashes, no
wall-clock reads, no live chain, no network. The matrix is pinned to the
waiver doc — a type added to or dropped from the waiver list without a
matching case fails ``test_waiver_doc_and_replay_matrix_agree``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from collections.abc import Callable

import pytest
from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import (
    Account,
    Block,
    Bond,
    ChainParameter,
    LiquidityPool,
    LiquidityStake,
    Receipt,
)
from aitbc_chain.base_models import Transaction as ChainTransaction
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.state.bridge_credit import sign_bridge_credit, sign_bridge_lock
from aitbc_chain.state.gpu_resources import GPURegistration
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import (
    _BOND_BURN_ADDRESS,
    _BOND_ESCROW_ADDRESS,
    StateTransition,
    use_account_nonce_override,
)
from aitbc_chain.state.pure_state_transition import _escrow_address
from sqlmodel import Session, create_engine, select

REPO_ROOT = Path(__file__).resolve().parents[2]
WAIVER_DOC = REPO_ROOT / "docs" / "decisions" / "v1-v9-live-exercise-waivers.md"

CHAIN = "v9-replay"
HEIGHT = 100  # block the replayed transaction lands in
LOCK_HEIGHT = 10  # seeded confirmed rows (locks) live here
V9 = 9

BUYER_KEY = "0x" + "11" * 32
PROVIDER_KEY = "0x" + "22" * 32
AUTH_KEY = "0x" + "33" * 32  # settlement/slash/governance/bridge authority

BUYER = derive_ethereum_address(BUYER_KEY)
PROVIDER = derive_ethereum_address(PROVIDER_KEY)
AUTH = derive_ethereum_address(AUTH_KEY)
NODE_WALLET = derive_ethereum_address("0x" + "66" * 32)


def _hash(*parts: object) -> str:
    return "0x" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _sign_data(private_key: str, data: dict) -> str:
    """Wallet-shaped signature over the canonical JSON minus ``signature`` —
    the convention ``verify_transaction_signature`` rebuilds."""
    from eth_utils import keccak

    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def _attach_sender_sig(tx: dict, private_key: str) -> dict:
    signable = {k: v for k, v in tx.items() if k != "signature"}
    if "amount" in signable:
        signable.pop("value", None)
    tx["signature"] = _sign_data(private_key, signable)
    return tx


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No env authority leakage — every gate is seeded on-chain."""
    metrics_registry.reset()
    monkeypatch.setattr(settings, "bridge_release_authority", "")
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.delenv("BRIDGE_RELEASE_AUTHORITY", raising=False)
    monkeypatch.delenv("ESCROW_RELEASE_ADDRESS", raising=False)
    monkeypatch.delenv("ESCROW_SETTLEMENT_AUTHORITY", raising=False)
    monkeypatch.delenv("BOND_SLASH_AUTHORITY_ADDRESS", raising=False)
    yield
    metrics_registry.reset()


def _new_engine(tmp_path, tag: str):
    engine = create_engine(f"sqlite:///{tmp_path / f'v9-replay-{tag}.db'}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def _account_rows(engine) -> dict[str, tuple[int, int]]:
    with Session(engine) as session:
        rows = session.exec(select(Account).where(Account.chain_id == CHAIN)).all()
        return {r.address: (r.balance, r.nonce) for r in rows}


def _state_root(engine) -> str | None:
    with Session(engine) as session:
        return compute_state_root_full(session, CHAIN)


# --------------------------------------------------------------------------
# seeds — identical on both databases
# --------------------------------------------------------------------------

ESCROW_JOB = "job-v9r-1"
ESCROW_ADDR = _escrow_address(ESCROW_JOB)
STAKE_LOCK_HASH = _hash("stake-lock", "v9r-1")
BRIDGE_LOCK_HASH = _hash("bridge-lock", "v9r-1")
RECEIPT_ID = _hash("receipt", "v9r-1")


def _seed_common(session: Session) -> None:
    """Funded actors + the authority parameters at unscoped height."""
    for addr in (BUYER, PROVIDER, AUTH, NODE_WALLET):
        session.add(Account(chain_id=CHAIN, address=addr, balance=10_000_000, nonce=0))
    for name, value in (
        ("escrow_settlement_authority", AUTH),
        ("bridge_release_authority", AUTH),
        ("governance_executors", AUTH),
        ("bond_slash_authority", AUTH),
    ):
        session.add(ChainParameter(chain_id=CHAIN, parameter=name, value=value, applied_height=None))
    session.add(
        Block(
            chain_id=CHAIN,
            height=LOCK_HEIGHT,
            hash=_hash("block", LOCK_HEIGHT),
            parent_hash="0x00",
            proposer="proposer-a",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            tx_count=0,
            block_metadata=json.dumps({"state_transition_version": 9}),
        )
    )


def _seed_escrow_lock(session: Session) -> None:
    session.add(Account(chain_id=CHAIN, address=ESCROW_ADDR, balance=7000, nonce=0))
    session.add(
        ChainTransaction(
            chain_id=CHAIN,
            tx_hash=_hash("escrow-lock", ESCROW_JOB),
            block_height=LOCK_HEIGHT,
            sender=BUYER,
            recipient=NODE_WALLET,
            payload={"job_id": ESCROW_JOB, "provider": PROVIDER},
            type="ESCROW_LOCK",
            value=7000,
            fee=DEFAULT_TX_FEE_UNITS,
            nonce=0,
            status="confirmed",
        )
    )


def _seed_stake_lock(session: Session) -> None:
    session.add(
        ChainTransaction(
            chain_id=CHAIN,
            tx_hash=STAKE_LOCK_HASH,
            block_height=LOCK_HEIGHT,
            sender=BUYER,
            recipient=BUYER,
            payload={"stake_id": "v9r-9"},
            type="STAKE_LOCK",
            value=4000,
            fee=0,
            nonce=0,
            status="confirmed",
        )
    )


def _seed_bridge_lock(session: Session) -> None:
    session.add(
        ChainTransaction(
            chain_id=CHAIN,
            tx_hash=BRIDGE_LOCK_HASH,
            block_height=LOCK_HEIGHT,
            sender=BUYER,
            recipient="bridge_lock",
            payload={"transfer_id": "xfer-v9r-1", "target_chain": "ait-side"},
            type="BRIDGE_LOCK",
            value=9000,
            fee=0,
            nonce=0,
            status="confirmed",
        )
    )


def _seed_gpu_registration(session: Session) -> None:
    session.add(
        GPURegistration(
            chain_id=CHAIN,
            gpu_id="gpu-v9r-1",
            miner_id="miner-v9r-1",
            model="RTX 4090",
            memory_gb=24,
            price_per_hour=Decimal("0.1"),
            registered_by=PROVIDER,
            status="active",
        )
    )


def _seed_liquidity(session: Session) -> None:
    from aitbc_chain.state.liquidity import pool_main_address, pool_treasury_address

    session.add(Account(chain_id=CHAIN, address=pool_main_address(), balance=10_000, nonce=0))
    # Treasury must hold the pending rewards the seeded stake can claim —
    # withdraw/claim check treasury >= accrued rewards before moving value.
    session.add(Account(chain_id=CHAIN, address=pool_treasury_address(), balance=100_000, nonce=0))
    session.add(LiquidityPool(pool_id="main", chain_id=CHAIN, total_staked=10_000, reward_per_share=Decimal("0.5")))
    session.add(
        LiquidityStake(
            stake_id="lstake-v9r-1",
            chain_id=CHAIN,
            pool_id="main",
            address=BUYER,
            amount=10_000,
            lock_days=0,
            locked_until=None,
            reward_per_share_at_stake=Decimal("0"),
            rewards_claimed=0,
            status="active",
        )
    )


def _seed_receipt(session: Session) -> None:
    session.add(
        Receipt(
            chain_id=CHAIN,
            job_id="job-v9r-rc",
            receipt_id=RECEIPT_ID,
            payload={"units": 12},
            miner_signature={"sig": "miner"},
            coordinator_attestations=[{"att": "coord"}],
            minted_amount=1234,
            status="pending",
        )
    )


def _seed_bond(session: Session) -> None:
    """An active 5000-unit bond for PROVIDER plus the escrow holding it."""
    session.add(Account(chain_id=CHAIN, address=_BOND_ESCROW_ADDRESS, balance=5000, nonce=0))
    session.add(Account(chain_id=CHAIN, address=_BOND_BURN_ADDRESS, balance=0, nonce=0))
    session.add(
        Bond(
            chain_id=CHAIN,
            bond_id="bond-v9r-1",
            provider=PROVIDER,
            amount=5000,
            locked_until=datetime(2020, 1, 1, tzinfo=UTC),
            status="active",
            created_tx_hash=_hash("bond-lock", "bond-v9r-1"),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )


def _bounty_escrow() -> str:
    from aitbc_chain.protocol_escrow import bounty_escrow_address

    return bounty_escrow_address()


def _seed_bounty_escrow(session: Session) -> None:
    session.add(Account(chain_id=CHAIN, address=_bounty_escrow(), balance=1_000_000, nonce=0))


def _seed_bond_escrow(session: Session) -> None:
    session.add(Account(chain_id=CHAIN, address=_BOND_ESCROW_ADDRESS, balance=0, nonce=0))


# --------------------------------------------------------------------------
# transaction builders — one per waived type
# --------------------------------------------------------------------------


def _tx(
    sender: str, recipient: str, value: int, tx_type: str, payload: dict | None = None, fee: int = DEFAULT_TX_FEE_UNITS
) -> dict:
    return {
        "from": sender,
        "to": recipient,
        "amount": value,
        "value": value,
        "fee": fee,
        "nonce": 0,
        "type": tx_type,
        "chain_id": CHAIN,
        "payload": payload or {},
    }


def _bridge_lock_tx() -> dict:
    tx = _tx(BUYER, "bridge_lock", 9000, "BRIDGE_LOCK", {"transfer_id": "xfer-v9r-1", "target_chain": "ait-side"})
    _attach_sender_sig(tx, BUYER_KEY)
    tx["tx_hash"] = _hash("bridge-lock-tx", "v9r")
    tx["bridge_signature"] = sign_bridge_lock(tx, tx["tx_hash"], AUTH_KEY)
    return tx


def _bridge_credit_tx(tx_type: str) -> dict:
    pseudo = "bridge_release" if tx_type == "BRIDGE_RELEASE" else "bridge_refund"
    tx = {
        "from": pseudo,
        "to": BUYER,
        "amount": 9000,
        "value": 9000,
        "fee": 0,
        "nonce": 0,
        "type": tx_type,
        "chain_id": CHAIN,
        "tx_hash": _hash(tx_type.lower(), "v9r"),
        "signature": "",
        "payload": {"transfer_id": "xfer-v9r-1", "asset": "AIT"},
    }
    if tx_type == "BRIDGE_REFUND":
        tx["payload"]["lock_tx_hash"] = BRIDGE_LOCK_HASH
        tx["lock_tx_hash"] = BRIDGE_LOCK_HASH
    tx["payload"]["bridge_signature"] = sign_bridge_credit(tx, tx["tx_hash"], AUTH_KEY)
    return tx


def _stake_escrow() -> str:
    from aitbc_chain.protocol_escrow import stake_escrow_address

    return stake_escrow_address()


def _bounty_protocol_tx(tx_type: str) -> dict:
    """The exact shape ``queue_protocol_transfer`` emits: unsigned top-level
    (the bounty escrow is keyless), operator authorization in
    ``payload.auth`` — signed by the operator over the payload message."""
    payload = {"bounty_id": "b-1"}
    if tx_type == "BOUNTY_PAYOUT":
        payload["submission_id"] = "s-1"
    tx = _tx(
        _bounty_escrow(),
        PROVIDER if tx_type == "BOUNTY_PAYOUT" else BUYER,
        6000,
        tx_type,
        payload,
        fee=0,
    )
    tx["payload"]["auth"] = {
        "signer": AUTH,
        "message": payload,
        "signature": _sign_data(AUTH_KEY, payload),
    }
    return tx


# type -> (tx builder, signer key | None for keyless/self-signing, seed fns)
# signer None = pseudo-sender/protocol-escrow shape (bridge credits, bounty
# payouts) where the signature is embedded by the builder or not required.
_CASES: dict[str, tuple[Callable[[], dict], str | None, tuple[Callable[[Session], None], ...]]] = {
    "AI_JOB": (
        lambda: _tx(
            BUYER,
            "ai_service",
            1000,
            "AI_JOB",
            {"job_type": "inference", "prompt": "hello", "payment": 1000, "parameters": {}},
        ),
        BUYER_KEY,
        (),
    ),
    "MESSAGE": (lambda: _tx(BUYER, PROVIDER, 0, "MESSAGE", {"text": "hi"}), BUYER_KEY, ()),
    "BOND_LOCK": (
        lambda: _tx(
            PROVIDER,
            _BOND_ESCROW_ADDRESS,
            5000,
            "BOND_LOCK",
            {"bond_id": "bond-v9r-1", "provider": PROVIDER, "lock_days": 7},
        ),
        PROVIDER_KEY,
        (_seed_bond_escrow,),
    ),
    "BOND_RELEASE": (
        lambda: _tx(PROVIDER, PROVIDER, 0, "BOND_RELEASE", {"bond_id": "bond-v9r-1", "provider": PROVIDER}),
        PROVIDER_KEY,
        (_seed_bond,),
    ),
    "BOND_SLASH": (
        lambda: _tx(
            AUTH,
            _BOND_BURN_ADDRESS,
            0,
            "BOND_SLASH",
            {"bond_id": "bond-v9r-1", "provider": PROVIDER, "amount": 2000},
        ),
        AUTH_KEY,
        (_seed_bond,),
    ),
    "BOUNTY_LOCK": (
        lambda: _tx(BUYER, _bounty_escrow(), 6000, "BOUNTY_LOCK", {"bounty_id": "b-1"}, fee=0),
        BUYER_KEY,
        (),
    ),
    "BOUNTY_PAYOUT": (
        lambda: _bounty_protocol_tx("BOUNTY_PAYOUT"),
        None,
        (_seed_bounty_escrow,),
    ),
    "BOUNTY_REFUND": (
        lambda: _bounty_protocol_tx("BOUNTY_REFUND"),
        None,
        (_seed_bounty_escrow,),
    ),
    "BRIDGE_LOCK": (_bridge_lock_tx, None, ()),
    "BRIDGE_RELEASE": (lambda: _bridge_credit_tx("BRIDGE_RELEASE"), None, ()),
    "BRIDGE_REFUND": (lambda: _bridge_credit_tx("BRIDGE_REFUND"), None, (_seed_bridge_lock,)),
    "BRIDGE_WITHDRAW": (
        lambda: _tx(BUYER, "bridge_burn", 3000, "BRIDGE_WITHDRAW", {"eth_address": PROVIDER}),
        BUYER_KEY,
        (),
    ),
    "GOVERNANCE_PROPOSE": (
        lambda: _tx(
            BUYER,
            BUYER,
            0,
            "GOVERNANCE_PROPOSE",
            {"proposal_id": "prop-v9r-1", "title": "t", "proposer": BUYER, "proposal_type": "general"},
        ),
        BUYER_KEY,
        (),
    ),
    "GOVERNANCE_VOTE": (
        lambda: _tx(
            AUTH,
            AUTH,
            0,
            "GOVERNANCE_VOTE",
            {"proposal_id": "prop-v9r-1", "voter": AUTH, "vote_type": "for"},
        ),
        AUTH_KEY,
        (),
    ),
    "GPU_ALLOCATE": (
        lambda: _tx(
            BUYER,
            BUYER,
            0,
            "GPU_ALLOCATE",
            {"gpu_id": "gpu-v9r-1", "client_id": BUYER, "duration_hours": 2.0, "total_cost": "0.2"},
        ),
        BUYER_KEY,
        (_seed_gpu_registration,),
    ),
    "IPFS_SUBSCRIPTION": (
        lambda: _tx(
            BUYER, PROVIDER, 100, "IPFS_SUBSCRIPTION", {"island_id": "isl-1", "duration_blocks": 10, "quota_bytes": 2048}
        ),
        BUYER_KEY,
        (),
    ),
    "LIQUIDITY_DEPOSIT": (
        lambda: _tx(BUYER, BUYER, 10_000, "LIQUIDITY_DEPOSIT", {"pool_id": "main", "lock_days": 0}),
        BUYER_KEY,
        (),
    ),
    "LIQUIDITY_WITHDRAW": (
        lambda: _tx(BUYER, BUYER, 0, "LIQUIDITY_WITHDRAW", {"pool_id": "main", "stake_id": "lstake-v9r-1"}),
        BUYER_KEY,
        (_seed_liquidity,),
    ),
    "LIQUIDITY_CLAIM": (
        lambda: _tx(BUYER, BUYER, 0, "LIQUIDITY_CLAIM", {"pool_id": "main", "stake_id": "lstake-v9r-1"}),
        BUYER_KEY,
        (_seed_liquidity,),
    ),
    "RECEIPT_CLAIM": (
        lambda: _tx(PROVIDER, PROVIDER, 0, "RECEIPT_CLAIM", {"receipt_id": RECEIPT_ID}),
        PROVIDER_KEY,
        (_seed_receipt,),
    ),
    "STAKE_LOCK": (
        lambda: _tx(BUYER, _stake_escrow(), 4000, "STAKE_LOCK", {"stake_id": "v9r-9", "lock_days": 30}),
        BUYER_KEY,
        (),
    ),
    "STAKE_RELEASE": (
        lambda: _tx(BUYER, BUYER, 4000, "STAKE_RELEASE", {"stake_id": "v9r-9", "lock_tx_hashes": [STAKE_LOCK_HASH]}, fee=0),
        BUYER_KEY,
        (_seed_stake_lock,),
    ),
}


def _prepare(tx: dict, version: int) -> dict:
    """The same pre-normalization the real callers apply before either path:
    the account-nonce override for unsigned/legacy txs."""
    tx = dict(tx)
    if use_account_nonce_override(tx, version):
        tx["nonce"] = 0
    return tx


def _replay_twice(tmp_path, tx: dict, tx_hash: str, seeds, version: int = V9) -> tuple[Any, Any, bool, str]:
    """Apply the tx on two identically-seeded DBs at ``version`` rules.

    Returns (accounts_a, root_a, ok_b, msg_b) — caller asserts the second
    verdict matches and both surfaces are identical.
    """
    eng_a = _new_engine(tmp_path, "a")
    eng_b = _new_engine(tmp_path, "b")
    for eng in (eng_a, eng_b):
        with Session(eng) as s:
            _seed_common(s)
            for seed in seeds:
                seed(s)
            s.commit()

    tx = _prepare(tx, version)
    with Session(eng_a) as s:
        ok_a, msg_a = StateTransition().apply_transaction(s, CHAIN, tx, tx_hash, block_version=version, block_height=HEIGHT)
        if ok_a:
            s.commit()
        else:
            s.rollback()
    with Session(eng_b) as s:
        ok_b, msg_b = StateTransition().apply_transaction(s, CHAIN, tx, tx_hash, block_version=version, block_height=HEIGHT)
        if ok_b:
            s.commit()
        else:
            s.rollback()
    return eng_a, eng_b, ok_a, msg_a, ok_b, msg_b


# Types whose only production emission shape is an *unsigned* protocol-
# escrow transfer (``queue_protocol_transfer`` — the escrow address is
# keyless, so no sender signature can ever exist). v9's signature rule
# exempts only BRIDGE_*; every other unsigned type is rejected at apply.
# These cases are strict-xfail pinned to that defect: the day a consensus
# change admits the ``payload.auth`` shape (or signs these properly) they
# flip to XPASS and fail the suite, forcing the waiver to be revisited.
_UNSEALABLE_UNSIGNED = {"BOUNTY_PAYOUT", "BOUNTY_REFUND"}


@pytest.mark.parametrize(
    "tx_type",
    [
        pytest.param(
            t,
            marks=(
                pytest.mark.xfail(
                    strict=True,
                    reason=(
                        f"{t} is only ever emitted unsigned by queue_protocol_transfer "
                        "(keyless escrow + payload.auth) and v9 admits unsigned only for "
                        "BRIDGE_* — unsealable at v9 until a consensus change; see "
                        "docs/decisions/v1-v9-live-exercise-waivers.md"
                    ),
                )
                if t in _UNSEALABLE_UNSIGNED
                else ()
            ),
        )
        for t in sorted(_CASES)
    ],
    ids=lambda t: t,
)
def test_v9_type_replayed(tx_type, tmp_path):
    """Replay the type's transaction on two identical fixture chains — same
    verdict, same final state — at state-transition version 9 rules."""
    build, signer, seeds = _CASES[tx_type]
    tx = build()
    if signer is not None:
        _attach_sender_sig(tx, signer)
    tx_hash = tx.get("tx_hash") or _hash("v9-replay", tx_type)

    eng_a, eng_b, ok_a, msg_a, ok_b, msg_b = _replay_twice(tmp_path, tx, tx_hash, seeds)

    # A type that cannot apply at all on a prepared fixture chain is not
    # replayable — the waiver in the doc then needs revisiting.
    assert ok_a, f"{tx_type} failed to apply on the fixture chain: {msg_a}"
    assert ok_b, f"{tx_type} replay diverged in verdict: first run ok, second said {msg_b}"
    assert _account_rows(eng_a) == _account_rows(eng_b), (
        f"{tx_type} replay produced different account rows:\n  first : {_account_rows(eng_a)}\n  second: {_account_rows(eng_b)}"
    )
    root_a, root_b = _state_root(eng_a), _state_root(eng_b)
    assert root_a is not None and root_a == root_b, f"{tx_type} replay produced different state roots: {root_a} vs {root_b}"
    eng_a.dispose()
    eng_b.dispose()


def test_replay_is_not_vacuous(tmp_path):
    """Sanity: an applied tx visibly moves state — a trivially empty apply
    would compare equal on both databases and pass vacuously."""
    tx = _attach_sender_sig(_tx(BUYER, PROVIDER, 0, "MESSAGE", {"text": "hi"}), BUYER_KEY)
    tx_hash = _hash("v9-replay", "MESSAGE-record")
    eng_seed = _new_engine(tmp_path, "seed")
    with Session(eng_seed) as s:
        _seed_common(s)
        s.commit()
    before = _account_rows(eng_seed)
    eng_a, eng_b, ok_a, msg_a, _, _ = _replay_twice(tmp_path, tx, tx_hash, ())
    assert ok_a, msg_a
    # value 0 but the fee moves: the sender's row must change on both runs
    assert _account_rows(eng_a)[BUYER] != before[BUYER]
    assert _account_rows(eng_a) == _account_rows(eng_b)
    eng_a.dispose()
    eng_b.dispose()


def test_waiver_doc_and_replay_matrix_agree():
    """The parametrized cases are exactly the types the waiver doc lists —
    add a type to the doc and this fails until a case exists; drop a case
    and the doc's waiver claim loses its executable proof."""
    listed = set(re.findall(r"test_v9_type_replayed\[([A-Z_]+)\]", WAIVER_DOC.read_text()))
    assert listed, "no types found in the waiver doc — doc moved or renamed?"
    missing = listed - set(_CASES)
    extra = set(_CASES) - listed
    assert not missing, f"waived types without a replay case: {sorted(missing)}"
    assert not extra, f"replay cases for types not waived (sealed under v9 already?): {sorted(extra)}"


# --------------------------------------------------------------------------
# BNT-1 — production-shape protocol transfers at v9
# --------------------------------------------------------------------------
#
# ``queue_protocol_transfer`` is the only emitter of these types and it
# never sets a top-level ``signature`` — a protocol-escrow address has no
# key (lock legs *could* be user-signed but the emitter does not do it
# either). ``v9_signature_verdict`` exempts only BRIDGE_*, so from height
# 30400 every one of these rejects at apply with ``missing_signature``.
# Live chain (node2 + hub, 2026-10-12): zero of these sealed since v9; the
# last STAKE_LOCK/RELEASE are at 11073/11042, BOUNTY_*/HTLC_* never.
#
# Each case below replays the *exact* emitted shape at v9 and is
# strict-xfail: the suite goes red the day a consensus change makes any of
# them seal *under v9 rules*, so the waiver/options decision cannot
# silently go stale. The v17 ruling that revived the auth'd emissions is
# pinned separately at the end of this file — under v17 rules the split is
# deliberate: emissions carrying ``payload.auth`` seal, emissions with no
# auth at all (AUTO_STAKE, HTLC_*) stay dead.

HTLC_ADDR = derive_ethereum_address("0x" + "88" * 32)  # stand-in for HTLC_CONTRACT_ADDRESS


def _protocol_shape(sender: str, recipient: str, tx_type: str, payload: dict, auth: dict | None) -> dict:
    """Mirror of ``queue_protocol_transfer``'s tx_data: fee 0, nonce 0,
    no top-level signature, optional ``payload.auth``."""
    tx = _tx(sender, recipient, 4000, tx_type, dict(payload), fee=0)
    if auth is not None:
        tx["payload"]["auth"] = auth
    return tx


def _operator_auth(message: dict) -> dict:
    return {"signer": AUTH, "message": message, "signature": _sign_data(AUTH_KEY, message)}


def _user_auth(message: dict) -> dict:
    return {"signer": BUYER, "message": message, "signature": _sign_data(BUYER_KEY, message)}


def _seed_stake_escrow_funded(session: Session) -> None:
    session.add(Account(chain_id=CHAIN, address=_stake_escrow(), balance=100_000, nonce=0))


def _seed_htlc_funded(session: Session) -> None:
    session.add(Account(chain_id=CHAIN, address=HTLC_ADDR, balance=100_000, nonce=0))


# emitter -> (tx builder, seeds). One row per (caller, type) pair in the audit.
_PROTOCOL_EMISSIONS: dict[str, tuple[Callable[[], dict], tuple[Callable[[Session], None], ...]]] = {
    # rpc/staking.py — user-staking lock, user-signed request in payload.auth
    "staking.STAKE_LOCK": (
        lambda: _protocol_shape(
            BUYER,
            _stake_escrow(),
            "STAKE_LOCK",
            {"stake_id": "9", "lock_days": 30},
            _user_auth({"action": "stake", "address": BUYER, "amount": 4000, "chain_id": CHAIN, "stake_id": "9"}),
        ),
        (),
    ),
    # rpc/staking.py — user-staking release
    "staking.STAKE_RELEASE": (
        lambda: _protocol_shape(
            _stake_escrow(),
            BUYER,
            "STAKE_RELEASE",
            {"stake_id": "v9r-9", "lock_tx_hashes": [STAKE_LOCK_HASH]},
            _user_auth({"action": "unstake", "address": BUYER, "chain_id": CHAIN, "stake_id": "v9r-9"}),
        ),
        (_seed_stake_lock, _seed_stake_escrow_funded),
    ),
    # rpc/agent_staking.py — operator-signed on the staker's behalf
    "agent_staking.STAKE_LOCK": (
        lambda: _protocol_shape(
            BUYER,
            _stake_escrow(),
            "STAKE_LOCK",
            {"agent_stake_id": "a-1", "lock_days": 7},
            _operator_auth({"user_address": BUYER, "amount": 4000, "chain_id": CHAIN}),
        ),
        (),
    ),
    "agent_staking.STAKE_RELEASE": (
        lambda: _protocol_shape(
            _stake_escrow(),
            BUYER,
            "STAKE_RELEASE",
            {"agent_stake_id": "v9r-9", "lock_tx_hashes": [STAKE_LOCK_HASH]},
            _operator_auth({"user_address": BUYER, "chain_id": CHAIN, "stake_id": "v9r-9"}),
        ),
        (_seed_stake_lock, _seed_stake_escrow_funded),
    ),
    # rpc/escrow_routes.py — AUTO_STAKE reinvestment, no auth at all
    "escrow_routes.AUTO_STAKE_LOCK": (
        lambda: _protocol_shape(
            BUYER, _stake_escrow(), "STAKE_LOCK", {"stake_id": "7", "source": "auto_stake", "lock_days": 30}, None
        ),
        (),
    ),
    # rpc/bounty.py — operator-signed
    "bounty.BOUNTY_LOCK": (
        lambda: _protocol_shape(
            BUYER,
            _bounty_escrow(),
            "BOUNTY_LOCK",
            {"bounty_id": "b-1"},
            _operator_auth({"creator_address": BUYER, "reward_amount": 4000, "chain_id": CHAIN, "bounty_id": "b-1"}),
        ),
        (),
    ),
    "bounty.BOUNTY_PAYOUT": (
        lambda: _protocol_shape(
            _bounty_escrow(),
            PROVIDER,
            "BOUNTY_PAYOUT",
            {"bounty_id": "b-1", "submission_id": "s-1"},
            _operator_auth({"bounty_id": "b-1", "submission_id": "s-1", "chain_id": CHAIN}),
        ),
        (_seed_bounty_escrow,),
    ),
    "bounty.BOUNTY_REFUND": (
        lambda: _protocol_shape(
            _bounty_escrow(),
            BUYER,
            "BOUNTY_REFUND",
            {"bounty_id": "b-1"},
            _operator_auth({"user_address": BUYER, "bounty_id": "b-1", "chain_id": CHAIN}),
        ),
        (_seed_bounty_escrow,),
    ),
    # contracts/htlc_contract.py — no auth; generic transfer semantics
    "htlc.HTLC_LOCK": (lambda: _protocol_shape(BUYER, HTLC_ADDR, "HTLC_LOCK", {"swap_id": "sw-1"}, None), ()),
    "htlc.HTLC_CLAIM": (
        lambda: _protocol_shape(HTLC_ADDR, PROVIDER, "HTLC_CLAIM", {"swap_id": "sw-1"}, None),
        (_seed_htlc_funded,),
    ),
    "htlc.HTLC_REFUND": (
        lambda: _protocol_shape(HTLC_ADDR, BUYER, "HTLC_REFUND", {"swap_id": "sw-1"}, None),
        (_seed_htlc_funded,),
    ),
}


@pytest.mark.parametrize(
    "emission",
    [
        pytest.param(
            name,
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    f"{name}: queue_protocol_transfer emits no top-level signature and v9 "
                    "exempts only BRIDGE_* — unsealable since height 30400 (BNT-1)"
                ),
            ),
        )
        for name in sorted(_PROTOCOL_EMISSIONS)
    ],
    ids=lambda n: n,
)
def test_protocol_transfer_production_shape_seals_at_v9(emission, tmp_path):
    """The exact shape each caller emits must apply at v9. It does not —
    strict-xfail pins the defect per (caller, type)."""
    build, seeds = _PROTOCOL_EMISSIONS[emission]
    tx = build()
    tx_hash = _hash("bnt1", emission)
    eng_a, eng_b, ok_a, msg_a, ok_b, _ = _replay_twice(tmp_path, tx, tx_hash, seeds)
    try:
        assert ok_a and ok_b, f"{emission}: {msg_a}"
    finally:
        eng_a.dispose()
        eng_b.dispose()


@pytest.mark.parametrize("emission", sorted(_PROTOCOL_EMISSIONS), ids=lambda n: n)
def test_protocol_transfer_rejection_reason_is_v9_signature_rule(emission, tmp_path):
    """Pin *why* each one fails: the v9 presence check, not a payload or
    balance defect — so the options paper's diagnosis stays executable."""
    build, seeds = _PROTOCOL_EMISSIONS[emission]
    tx = build()
    tx_hash = _hash("bnt1-reason", emission)
    eng_a, eng_b, ok_a, msg_a, _, _ = _replay_twice(tmp_path, tx, tx_hash, seeds)
    try:
        assert not ok_a
        assert "v9 signature rule: missing_signature" in msg_a, f"{emission} rejected for another reason: {msg_a}"
    finally:
        eng_a.dispose()
        eng_b.dispose()


# --------------------------------------------------------------------------
# BNT-1 v17 — the ruling's revival half (operator decision 28 Oct).
#
# From ``state_transition_v17_height`` the signature rule additionally
# admits the five protocol-transfer types carrying a well-formed
# ``payload.auth`` (``V17_PAYLOAD_AUTH_TX_TYPES``), and the existing
# binding check re-verifies the auth as the authorization. Replayed at v17
# below: every emission that embeds auth seals — twice, for determinism —
# while emitters that carry no auth at all (escrow_routes AUTO_STAKE
# reinvestment, HTLC_*) stay rejected with the exact v9 verdict they had
# before. v17 admits the payload.auth shape, not unsigned transfers
# generally.

V17 = 17

_REVIVED_AT_V17 = {
    "staking.STAKE_LOCK",
    "staking.STAKE_RELEASE",
    "agent_staking.STAKE_LOCK",
    "agent_staking.STAKE_RELEASE",
    "bounty.BOUNTY_LOCK",
    "bounty.BOUNTY_PAYOUT",
    "bounty.BOUNTY_REFUND",
}


@pytest.mark.parametrize("emission", sorted(_PROTOCOL_EMISSIONS), ids=lambda n: n)
def test_protocol_transfer_production_shape_at_v17(emission, tmp_path):
    """The v17 ruling, replayed: auth-carrying emissions seal identically on
    two databases; no-auth emissions keep their v9 rejection."""
    build, seeds = _PROTOCOL_EMISSIONS[emission]
    tx = build()
    tx_hash = _hash("bnt1-v17", emission)
    eng_a, eng_b, ok_a, msg_a, ok_b, _ = _replay_twice(tmp_path, tx, tx_hash, seeds, version=V17)
    try:
        if emission in _REVIVED_AT_V17:
            assert ok_a and ok_b, f"{emission}: {msg_a}"
            assert _account_rows(eng_a) == _account_rows(eng_b)
            assert _state_root(eng_a) == _state_root(eng_b)
        else:
            assert not ok_a
            assert "v9 signature rule: missing_signature" in msg_a, f"{emission} rejected for another reason: {msg_a}"
    finally:
        eng_a.dispose()
        eng_b.dispose()
