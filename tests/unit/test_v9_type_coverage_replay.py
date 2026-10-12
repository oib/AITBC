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


def _replay_twice(tmp_path, tx: dict, tx_hash: str, seeds) -> tuple[Any, Any, bool, str]:
    """Apply the tx on two identically-seeded DBs at v9 rules.

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

    tx = _prepare(tx, V9)
    with Session(eng_a) as s:
        ok_a, msg_a = StateTransition().apply_transaction(s, CHAIN, tx, tx_hash, block_version=V9, block_height=HEIGHT)
        if ok_a:
            s.commit()
        else:
            s.rollback()
    with Session(eng_b) as s:
        ok_b, msg_b = StateTransition().apply_transaction(s, CHAIN, tx, tx_hash, block_version=V9, block_height=HEIGHT)
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
