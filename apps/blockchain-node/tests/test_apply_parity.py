"""Apply-path parity matrix — sequential ``apply_transaction`` vs the pure
``compute_state_delta`` + ``apply_deltas_to_db`` path (v0.25.8).

For every transaction type that has ever sealed on the fleet (plus GPU_DEREGISTER,
which activates at v10), at block versions 8, 9 and 10, under three signature
modes (``valid`` / ``absent`` / ``invalid``):

* the accept/reject verdict must agree: ``ok_seq == delta.success``;
* when both accept, the resulting ``account`` rows and the full state root
  must be identical on two identically-seeded databases;
* types the pure path deliberately does not model must be in
  ``SEQUENTIAL_ONLY_TX_TYPES`` and must come back with
  ``delta.requires_sequential`` — one canonical list, checked here so a
  future type can't silently fall through a generic delta.

The pure-side context arguments (``escrow_context``, ``bridge_authority``,
``bridge_lock_context``) are resolved through the same helpers the real
callers use (``build_escrow_context``, ``_bridge_release_authority``,
``build_bridge_lock_context``) against the identical seeded database — the
same way ``sync_block_import``/``consensus.poa`` prefetch them.

Fixtures are fully deterministic: fixed keys, fixed hashes, no wall-clock
reads, no ``uuid4``/``secrets`` — the nondeterministic service fields the
digest layer excludes (``allocation_id``, ``stake_id``, timestamps) never
enter the compared surface anyway.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

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
from aitbc_chain.state.pure_state_transition import (
    SEQUENTIAL_ONLY_TX_TYPES,
    apply_deltas_to_db,
    compute_state_delta,
)
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import (
    _BOND_BURN_ADDRESS,
    _BOND_ESCROW_ADDRESS,
    _bridge_release_authority,
    StateTransition,
    build_bridge_lock_context,
    build_escrow_context,
)
from aitbc_chain.state.pure_state_transition import _escrow_address
from sqlmodel import Session, create_engine, select

CHAIN = "parity-chain"
HEIGHT = 100  # block the transaction applies in
LOCK_HEIGHT = 10  # seeded confirmed rows (locks) live here
VERSIONS = (8, 9, 10)
MODES = ("valid", "absent", "invalid")

BUYER_KEY = "0x" + "11" * 32
PROVIDER_KEY = "0x" + "22" * 32
AUTH_KEY = "0x" + "33" * 32  # settlement/slash/governance/bridge authority
OTHER_KEY = "0x" + "77" * 32

BUYER = derive_ethereum_address(BUYER_KEY)
PROVIDER = derive_ethereum_address(PROVIDER_KEY)
AUTH = derive_ethereum_address(AUTH_KEY)
NODE_WALLET = derive_ethereum_address("0x" + "66" * 32)


def _hash(*parts: object) -> str:
    return "0x" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _sign_data(private_key: str, data: dict) -> str:
    """Wallet-shaped signature over the canonical JSON minus ``signature``.

    Same convention test_block_deltas_differential uses — it is what
    ``verify_transaction_signature`` rebuilds.
    """
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
    engine = create_engine(f"sqlite:///{tmp_path / f'parity-{tag}.db'}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def _account_rows(engine) -> dict[str, tuple[int, int]]:
    """All account rows as {address: (balance, nonce)} — the whole compared
    surface, sorted by key implicitly through dict equality."""
    with Session(engine) as session:
        rows = session.exec(select(Account).where(Account.chain_id == CHAIN)).all()
        return {r.address: (r.balance, r.nonce) for r in rows}


def _state_root(engine) -> str | None:
    with Session(engine) as session:
        return compute_state_root_full(session, CHAIN)


# --------------------------------------------------------------------------
# seeds — identical on both databases
# --------------------------------------------------------------------------

ESCROW_JOB = "job-par-1"
ESCROW_ADDR = _escrow_address(ESCROW_JOB)
STAKE_LOCK_HASH = _hash("stake-lock", "par-1")
BRIDGE_LOCK_HASH = _hash("bridge-lock", "par-1")
RECEIPT_ID = _hash("receipt", "par-1")


def _seed_common(session: Session) -> None:
    """Funded actors + the three authority parameters at unscoped height."""
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
            # Recorded version wins below the v8 threshold (24800) — the
            # seeded locks must look like they were mined under v>=3 rules.
            block_metadata=json.dumps({"state_transition_version": 9}),
        )
    )


def _seed_escrow_lock(session: Session) -> None:
    """Confirmed v>=3 lock for ``ESCROW_JOB`` plus its funded escrow address."""
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
    """Confirmed matured STAKE_LOCK owned by BUYER (the release payee)."""
    session.add(
        ChainTransaction(
            chain_id=CHAIN,
            tx_hash=STAKE_LOCK_HASH,
            block_height=LOCK_HEIGHT,
            sender=BUYER,
            recipient=BUYER,
            payload={"stake_id": "par-9"},  # no lock_days -> matured
            type="STAKE_LOCK",
            value=4000,
            fee=0,
            nonce=0,
            status="confirmed",
        )
    )


def _seed_bridge_lock(session: Session) -> None:
    """Confirmed BRIDGE_LOCK the refund binds to (v6+)."""
    session.add(
        ChainTransaction(
            chain_id=CHAIN,
            tx_hash=BRIDGE_LOCK_HASH,
            block_height=LOCK_HEIGHT,
            sender=BUYER,
            recipient="bridge_lock",
            payload={"transfer_id": "xfer-par-1", "target_chain": "ait-side"},
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
            gpu_id="gpu-par-1",
            miner_id="miner-par-1",
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
    session.add(Account(chain_id=CHAIN, address=pool_treasury_address(), balance=0, nonce=0))
    session.add(LiquidityPool(pool_id="main", chain_id=CHAIN, total_staked=10_000, reward_per_share=Decimal("0.5")))
    session.add(
        LiquidityStake(
            stake_id="lstake-par-1",
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
            job_id="job-par-rc",
            receipt_id=RECEIPT_ID,
            payload={"units": 12},
            miner_signature={"sig": "miner"},
            coordinator_attestations=[{"att": "coord"}],
            minted_amount=1234,
            status="pending",
        )
    )


def _seed_bond_escrow(session: Session) -> None:
    session.add(Account(chain_id=CHAIN, address=_BOND_ESCROW_ADDRESS, balance=0, nonce=0))


def _seed_bond(session: Session) -> None:
    """An active 5000-unit bond for PROVIDER, locked until a past timestamp,
    plus the escrow account holding it — BOND_RELEASE/SLASH inputs."""
    _seed_bond_escrow(session)
    session.add(Account(chain_id=CHAIN, address=_BOND_BURN_ADDRESS, balance=0, nonce=0))
    session.add(
        Bond(
            chain_id=CHAIN,
            bond_id="bond-par-1",
            provider=PROVIDER,
            amount=5000,
            locked_until=datetime(2020, 1, 1, tzinfo=UTC),
            status="active",
            created_tx_hash=_hash("bond-lock", "bond-par-1"),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    # The escrow actually holds the bonded value.
    esc = session.get(Account, (CHAIN, _BOND_ESCROW_ADDRESS))
    assert esc is not None
    esc.balance = 5000


# --------------------------------------------------------------------------
# transaction builders — one per type, mode-mutated by the harness
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


# name -> (tx builder, signer key | None, seeds, sequential-only?)
# signer key None => keyless/pseudo-sender shape (signature handled per case).
def _cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    def add(name, build, signer, seeds=()):
        cases.append({"name": name, "build": build, "signer": signer, "seeds": seeds})

    add("transfer", lambda: _tx(BUYER, PROVIDER, 5000, "TRANSFER"), BUYER_KEY)
    add("transfer-overspend", lambda: _tx(BUYER, PROVIDER, 10**30, "TRANSFER"), BUYER_KEY)
    add("message", lambda: _tx(BUYER, PROVIDER, 0, "MESSAGE", {"text": "hi"}), BUYER_KEY)
    add("exchange", lambda: _tx(BUYER, PROVIDER, 100, "EXCHANGE", {"action": "buy", "order_id": "o-1"}), BUYER_KEY)
    add(
        "gpu_market",
        lambda: _tx(BUYER, BUYER, 0, "GPU_MARKET", {"action": "offer", "offer_id": "of-1", "gpu_id": "g-1"}),
        BUYER_KEY,
    )
    add(
        "gpu_marketplace",
        lambda: _tx(BUYER, PROVIDER, 100, "GPU_MARKETPLACE", {"action": "software_offer", "offer_id": "sw-1"}),
        BUYER_KEY,
    )
    add(
        "governance_propose",
        lambda: _tx(
            BUYER,
            BUYER,
            0,
            "GOVERNANCE_PROPOSE",
            {"proposal_id": "prop-par-1", "title": "t", "proposer": BUYER, "proposal_type": "general"},
        ),
        BUYER_KEY,
    )
    add(
        "governance_vote",
        lambda: _tx(
            AUTH,
            AUTH,
            0,
            "GOVERNANCE_VOTE",
            {"proposal_id": "prop-par-1", "voter": AUTH, "vote_type": "for"},
        ),
        AUTH_KEY,
    )
    add(
        "governance_execute",
        lambda: _tx(
            AUTH,
            AUTH,
            0,
            "GOVERNANCE_EXECUTE",
            {
                "proposal_id": "prop-par-1",
                "executor": AUTH,
                "execution_payload": {"action": "parameter_change", "parameter": "parity_probe", "value": "1"},
            },
        ),
        AUTH_KEY,
    )
    add(
        "escrow_lock",
        lambda: _tx(BUYER, NODE_WALLET, 7000, "ESCROW_LOCK", {"job_id": ESCROW_JOB, "provider": PROVIDER}),
        BUYER_KEY,
    )
    add(
        "escrow_release",
        lambda: _tx(AUTH, PROVIDER, 7000, "ESCROW_RELEASE", {"job_id": ESCROW_JOB}),
        AUTH_KEY,
        seeds=(_seed_escrow_lock,),
    )
    add(
        "escrow_refund",
        lambda: _tx(AUTH, BUYER, 7000, "ESCROW_REFUND", {"job_id": ESCROW_JOB}),
        AUTH_KEY,
        seeds=(_seed_escrow_lock,),
    )
    add(
        "stake_lock",
        lambda: _tx(BUYER, _stake_escrow(), 4000, "STAKE_LOCK", {"stake_id": "par-9", "lock_days": 30}),
        BUYER_KEY,
    )
    add(
        "stake_release",
        lambda: _tx(BUYER, BUYER, 4000, "STAKE_RELEASE", {"stake_id": "par-9", "lock_tx_hashes": [STAKE_LOCK_HASH]}, fee=0),
        BUYER_KEY,
        seeds=(_seed_stake_lock,),
    )
    add(
        "liquidity_deposit",
        lambda: _tx(BUYER, BUYER, 10_000, "LIQUIDITY_DEPOSIT", {"pool_id": "main", "lock_days": 0}),
        BUYER_KEY,
    )
    add(
        "liquidity_withdraw",
        lambda: _tx(BUYER, BUYER, 0, "LIQUIDITY_WITHDRAW", {"pool_id": "main", "stake_id": "lstake-par-1"}),
        BUYER_KEY,
        seeds=(_seed_liquidity,),
    )
    add(
        "liquidity_claim",
        lambda: _tx(BUYER, BUYER, 0, "LIQUIDITY_CLAIM", {"pool_id": "main", "stake_id": "lstake-par-1"}),
        BUYER_KEY,
        seeds=(_seed_liquidity,),
    )
    add(
        "gpu_register",
        lambda: _tx(
            PROVIDER,
            PROVIDER,
            0,
            "GPU_REGISTER",
            {"gpu_id": "gpu-par-1", "miner_id": "miner-par-1", "model": "RTX 4090", "memory_gb": 24, "price_per_hour": "0.1"},
        ),
        PROVIDER_KEY,
    )
    add(
        "gpu_allocate",
        lambda: _tx(
            BUYER,
            BUYER,
            0,
            "GPU_ALLOCATE",
            {"gpu_id": "gpu-par-1", "client_id": BUYER, "duration_hours": 2.0, "total_cost": "0.2"},
        ),
        BUYER_KEY,
        seeds=(_seed_gpu_registration,),
    )
    add(
        "gpu_deregister",
        lambda: _tx(PROVIDER, PROVIDER, 0, "GPU_DEREGISTER", {"gpu_id": "gpu-par-1"}),
        PROVIDER_KEY,
        seeds=(_seed_gpu_registration,),
    )
    add(
        "ipfs_subscription",
        lambda: _tx(
            BUYER, PROVIDER, 100, "IPFS_SUBSCRIPTION", {"island_id": "isl-1", "duration_blocks": 10, "quota_bytes": 2048}
        ),
        BUYER_KEY,
    )
    add(
        "bond_lock",
        lambda: _tx(
            PROVIDER, _BOND_ESCROW_ADDRESS, 5000, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": PROVIDER, "lock_days": 7}
        ),
        PROVIDER_KEY,
        seeds=(_seed_bond_escrow,),
    )
    add(
        "bond_release",
        lambda: _tx(PROVIDER, PROVIDER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}),
        PROVIDER_KEY,
        seeds=(_seed_bond,),
    )
    add(
        "bond_slash",
        lambda: _tx(
            AUTH, _BOND_BURN_ADDRESS, 0, "BOND_SLASH", {"bond_id": "bond-par-1", "provider": PROVIDER, "amount": 2000}
        ),
        AUTH_KEY,
        seeds=(_seed_bond,),
    )
    add(
        "receipt_claim",
        lambda: _tx(PROVIDER, PROVIDER, 0, "RECEIPT_CLAIM", {"receipt_id": RECEIPT_ID}),
        PROVIDER_KEY,
        seeds=(_seed_receipt,),
    )
    add(
        "bridge_withdraw",
        lambda: _tx(BUYER, "bridge_burn", 3000, "BRIDGE_WITHDRAW", {"eth_address": PROVIDER}),
        BUYER_KEY,
    )
    add(
        "bounty_payout",
        lambda: _tx(_bounty_escrow(), PROVIDER, 6000, "BOUNTY_PAYOUT", {"bounty_id": "b-1", "submission_id": "s-1"}, fee=0),
        None,  # keyless protocol-escrow sender
        seeds=(_seed_bounty_escrow,),
    )
    return cases


def _stake_escrow() -> str:
    from aitbc_chain.protocol_escrow import stake_escrow_address

    return stake_escrow_address()


def _bounty_escrow() -> str:
    from aitbc_chain.protocol_escrow import bounty_escrow_address

    return bounty_escrow_address()


def _seed_bounty_escrow(session: Session) -> None:
    session.add(Account(chain_id=CHAIN, address=_bounty_escrow(), balance=1_000_000, nonce=0))


def _bridge_lock_tx(mode: str) -> dict:
    tx = _tx(BUYER, "bridge_lock", 9000, "BRIDGE_LOCK", {"transfer_id": "xfer-par-1", "target_chain": "ait-side"})
    _attach_sender_sig(tx, BUYER_KEY)  # sender signature stays valid; the
    # varied dimension is the authority's bridge_signature.
    tx["tx_hash"] = _hash("bridge-lock-tx", mode)
    if mode == "valid":
        tx["bridge_signature"] = sign_bridge_lock(tx, tx["tx_hash"], AUTH_KEY)
    elif mode == "invalid":
        tx["bridge_signature"] = sign_bridge_lock(tx, tx["tx_hash"], OTHER_KEY)
    return tx


def _bridge_credit_tx(tx_type: str, mode: str) -> dict:
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
        "tx_hash": _hash(tx_type.lower(), "par", mode),
        "signature": "",
        "payload": {"transfer_id": "xfer-par-1", "asset": "AIT"},
    }
    if tx_type == "BRIDGE_REFUND":
        tx["payload"]["lock_tx_hash"] = BRIDGE_LOCK_HASH
        tx["lock_tx_hash"] = BRIDGE_LOCK_HASH
    if mode == "valid":
        tx["payload"]["bridge_signature"] = sign_bridge_credit(tx, tx["tx_hash"], AUTH_KEY)
    elif mode == "invalid":
        tx["payload"]["bridge_signature"] = sign_bridge_credit(tx, tx["tx_hash"], OTHER_KEY)
    return tx


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------


def _prepare(tx: dict, version: int) -> dict:
    """Apply the same pre-normalization the real callers do before either
    path: the account-nonce override for unsigned/legacy txs."""
    from aitbc_chain.state.state_transition import use_account_nonce_override

    tx = dict(tx)
    if use_account_nonce_override(tx, version):
        # Fresh seeded accounts all sit at nonce 0 — same substitution the
        # sync/proposer callers do against account_map.
        tx["nonce"] = 0
    return tx


def _run_pair(tmp_path, tx: dict, tx_hash: str, version: int, seeds) -> tuple:
    """Run the same tx through both paths on identical seeded DBs.

    Returns (ok_seq, msg_seq, delta) — account/root comparison happens in the
    caller once the delta verdict is known.
    """
    eng_seq = _new_engine(tmp_path, "seq")
    eng_pure = _new_engine(tmp_path, "pure")
    try:
        for eng in (eng_seq, eng_pure):
            with Session(eng) as s:
                _seed_common(s)
                for seed in seeds:
                    seed(s)
                s.commit()

        tx = _prepare(tx, version)

        with Session(eng_seq) as s:
            st = StateTransition()
            ok_seq, msg_seq = st.apply_transaction(s, CHAIN, tx, tx_hash, block_version=version, block_height=HEIGHT)
            if ok_seq:
                s.commit()
            else:
                # A rejected tx leaves only discarded session state — same as
                # production, where a failed apply aborts the block.
                s.rollback()

        with Session(eng_pure) as s:
            account_map = {
                a.address: Account(chain_id=a.chain_id, address=a.address, balance=a.balance, nonce=a.nonce)
                for a in s.exec(select(Account).where(Account.chain_id == CHAIN)).all()
            }
            escrow_ctx = build_escrow_context(s, CHAIN, [tx], block_height=HEIGHT)
            bridge_ctx = build_bridge_lock_context(s, CHAIN, [tx])
            bridge_authority = _bridge_release_authority(s, CHAIN, HEIGHT)
            delta = compute_state_delta(
                account_map,
                tx,
                CHAIN,
                tx_hash,
                set(),
                block_version=version,
                escrow_context=escrow_ctx,
                bridge_authority=bridge_authority,
                bridge_lock_context=bridge_ctx,
            )
            if delta.success and not delta.requires_sequential:
                apply_deltas_to_db(s, [delta], CHAIN, block_version=version)
                s.commit()
        return eng_seq, eng_pure, ok_seq, msg_seq, delta
    except Exception:
        eng_seq.dispose()
        eng_pure.dispose()
        raise


CASES = _cases()


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_sequential_vs_pure_parity(case, mode, version, tmp_path):
    """One cell of the matrix: verdict agreement + identical account state."""
    tx = case["build"]()
    signer = case["signer"]
    if signer is None:
        # Keyless protocol-escrow sender: there is no key that could produce a
        # valid signature, so "valid" is not a real mode — skip it.
        if mode == "valid":
            pytest.skip("keyless pseudo-sender cannot produce a valid sender signature")
        if mode == "invalid":
            _attach_sender_sig(tx, OTHER_KEY)
        # absent: leave unsigned
    elif mode == "valid":
        _attach_sender_sig(tx, signer)
    elif mode == "invalid":
        _attach_sender_sig(tx, OTHER_KEY)
    # absent: leave unsigned

    tx_hash = _hash("parity", case["name"], mode, version)
    eng_seq, eng_pure, ok_seq, msg_seq, delta = _run_pair(tmp_path, tx, tx_hash, version, case["seeds"])

    seq_only = delta.tx_type in SEQUENTIAL_ONLY_TX_TYPES
    if seq_only:
        # Contract: the pure path explicitly refuses to model these types —
        # either via the flag (defense in depth) or via caller pre-filtering.
        # Account parity is vacuous: production always applies them
        # sequentially, which is what the sequential run above already did.
        assert delta.requires_sequential, (
            f"{delta.tx_type} is in SEQUENTIAL_ONLY_TX_TYPES but the pure "
            f"path returned a modelable delta ({delta.error or 'success'})"
        )
    else:
        assert ok_seq == delta.success, (
            f"{case['name']}[{mode}]@v{version}: sequential={ok_seq} ({msg_seq}) "
            f"but pure delta success={delta.success} ({delta.error})"
        )
        if ok_seq:
            assert _account_rows(eng_seq) == _account_rows(eng_pure), (
                f"{case['name']}[{mode}]@v{version}: account rows diverge\n"
                f"  seq : {_account_rows(eng_seq)}\n  pure: {_account_rows(eng_pure)}"
            )
            assert _state_root(eng_seq) == _state_root(eng_pure)
    eng_seq.dispose()
    eng_pure.dispose()


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", MODES)
def test_bridge_lock_parity(mode, version, tmp_path):
    """BRIDGE_LOCK: sender-signed + the v9 bridge_signature authority gate."""
    tx = _bridge_lock_tx(mode)
    eng_seq, eng_pure, ok_seq, msg_seq, delta = _run_pair(tmp_path, tx, tx["tx_hash"], version, ())
    assert "BRIDGE_LOCK" not in SEQUENTIAL_ONLY_TX_TYPES
    assert ok_seq == delta.success, (
        f"BRIDGE_LOCK[{mode}]@v{version}: sequential={ok_seq} ({msg_seq}) vs pure={delta.success} ({delta.error})"
    )
    if ok_seq:
        assert _account_rows(eng_seq) == _account_rows(eng_pure)
        assert _state_root(eng_seq) == _state_root(eng_pure)
    eng_seq.dispose()
    eng_pure.dispose()


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("tx_type", ("BRIDGE_RELEASE", "BRIDGE_REFUND"))
def test_bridge_credit_parity(tx_type, mode, version, tmp_path):
    """Pseudo-sender credits: bridge_signature valid/absent/wrong-key."""
    seeds = (_seed_bridge_lock,) if tx_type == "BRIDGE_REFUND" else ()
    tx = _bridge_credit_tx(tx_type, mode)
    eng_seq, eng_pure, ok_seq, msg_seq, delta = _run_pair(tmp_path, tx, tx["tx_hash"], version, seeds)
    assert ok_seq == delta.success, (
        f"{tx_type}[{mode}]@v{version}: sequential={ok_seq} ({msg_seq}) vs pure={delta.success} ({delta.error})"
    )
    if ok_seq:
        assert _account_rows(eng_seq) == _account_rows(eng_pure)
        assert _state_root(eng_seq) == _state_root(eng_pure)
    eng_seq.dispose()
    eng_pure.dispose()


# --------------------------------------------------------------------------
# targeted non-matrix cases
# --------------------------------------------------------------------------


def test_replay_rejected_identically(tmp_path):
    """A tx whose hash is already sealed must fail on both paths (v8)."""
    tx = _attach_sender_sig(_tx(BUYER, PROVIDER, 100, "TRANSFER"), BUYER_KEY)
    tx_hash = _hash("parity-replay")

    def seed_replay(session: Session) -> None:
        session.add(
            ChainTransaction(
                chain_id=CHAIN,
                tx_hash=tx_hash,
                block_height=LOCK_HEIGHT,
                sender=BUYER,
                recipient=PROVIDER,
                type="TRANSFER",
                value=100,
                status="confirmed",
            )
        )

    eng_seq = _new_engine(tmp_path, "seq")
    eng_pure = _new_engine(tmp_path, "pure")
    for eng in (eng_seq, eng_pure):
        with Session(eng) as s:
            _seed_common(s)
            seed_replay(s)
            s.commit()
    with Session(eng_seq) as s:
        ok_seq, msg_seq = StateTransition().apply_transaction(s, CHAIN, tx, tx_hash, block_version=8, block_height=HEIGHT)
    with Session(eng_pure) as s:
        account_map = {
            a.address: Account(chain_id=a.chain_id, address=a.address, balance=a.balance, nonce=a.nonce)
            for a in s.exec(select(Account).where(Account.chain_id == CHAIN)).all()
        }
        delta = compute_state_delta(account_map, tx, CHAIN, tx_hash, {tx_hash}, block_version=8)
    assert ok_seq is False and delta.success is False, (msg_seq, delta.error)
    eng_seq.dispose()
    eng_pure.dispose()


def test_signed_wrong_nonce_rejected_identically(tmp_path):
    """Signed tx whose nonce mismatches the account fails on both paths (v9)."""
    tx = _attach_sender_sig(_tx(BUYER, PROVIDER, 100, "TRANSFER"), BUYER_KEY)
    tx["nonce"] = 7  # signed-over field changed after signing: invalid sig AND nonce
    # Re-sign so the signature is valid but the nonce is wrong — isolates the
    # nonce gate, not the signature gate.
    _attach_sender_sig(tx, BUYER_KEY)
    eng_seq, eng_pure, ok_seq, msg_seq, delta = _run_pair(tmp_path, tx, _hash("nonce-par"), 9, ())
    assert ok_seq is False and delta.success is False, (msg_seq, delta.error)
    eng_seq.dispose()
    eng_pure.dispose()


def test_sequential_only_sets_are_the_single_list():
    """The caller routing sets and the pure-path contract must be one list —
    the v9 policy lesson: three copies that can drift is how the gaps got in."""
    from aitbc_chain.consensus import poa
    from aitbc_chain import sync_block_import

    assert poa._SEQUENTIAL_ONLY_TX_TYPES == SEQUENTIAL_ONLY_TX_TYPES
    assert sync_block_import._SEQUENTIAL_ONLY_TX_TYPES == SEQUENTIAL_ONLY_TX_TYPES
    # every member is covered by a matrix case
    covered = {c["build"]().get("type") for c in CASES} | {"BRIDGE_LOCK", "BRIDGE_RELEASE", "BRIDGE_REFUND"}
    missing = SEQUENTIAL_ONLY_TX_TYPES - covered
    assert not missing, f"sequential-only types without parity coverage: {missing}"
