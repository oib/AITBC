"""#2745 phase-2: rejection-aware nonce reuse end to end.

A consensus-rejected resubmission keeps its deterministic hash parked in a
follower's mempool while the durable ``Transaction`` row says ``rejected``.
The opt-in ``?nonce_view=true`` mempool read stops counting those dead
occupants, ``--retry-rejected`` signs a fresh ``attempt_id`` envelope into
the freed slot, admission evicts the dead occupant through the real
``_evict_apply_rejected_occupant`` path, and a real proposer pipeline seals
it — all in-process, no network, no stubbed signature or apply.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from eth_keys import keys
from fastapi import Request
from sqlmodel import Session, create_engine, select
from sqlmodel.pool import StaticPool

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.mempool import DatabaseMempool, InMemoryMempool
from aitbc_chain.mempool_common import compute_tx_hash
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Block, LiquidityStake, Transaction
from aitbc_chain.rpc import transactions as txmod
from aitbc_chain.rpc.transactions import TransactionRequest
from aitbc_chain.rpc.utils import (
    normalize_transaction_data,
    sign_transaction_data,
    verify_transaction_signature,
)
from aitbc_chain.state.liquidity import pool_main_address, pool_treasury_address
from aitbc_chain.state.state_transition import get_state_transition

from .test_liquidity import _fund_pool_account, _seed_active_stake

# ``aitbc_cli`` resolves through the venv's editable install (-> /opt/aitbc)
# unless cli/ is on sys.path — cli/tests/conftest.py inserts it for the CLI
# suite, but this file must also work standalone, so bootstrap the same path
# before any deferred ``aitbc_cli`` import below runs.
_CLI_DIR = Path(__file__).resolve().parents[3] / "cli"
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

CHAIN = "test-chain"
PK_HEX = "11" * 32
SENDER = keys.PrivateKey(bytes.fromhex(PK_HEX)).public_key.to_checksum_address()
STAKE_ID = "liq_retry_2745"
OTHER_KEY = "22" * 32
OTHER_SENDER = keys.PrivateKey(bytes.fromhex(OTHER_KEY)).public_key.to_checksum_address()


def _http_request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 40000),
            "query_string": b"",
        }
    )


def _maybe_await(result):
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result


def _withdraw_tx(sender: str, nonce: int, stake_id: str, chain_id: str = CHAIN) -> dict:
    """A normalized, really-signed LIQUIDITY_WITHDRAW envelope."""
    tx = {
        "type": "LIQUIDITY_WITHDRAW",
        "from": sender,
        "to": sender,
        "chain_id": chain_id,
        "amount": 0,
        "nonce": nonce,
        "fee": DEFAULT_TX_FEE_UNITS,
        "payload": {"pool_id": "main", "stake_id": stake_id, "to": sender, "amount": 36_000_000},
    }
    tx["signature"] = sign_transaction_data(tx, PK_HEX)
    return normalize_transaction_data(tx, chain_id)


def _seed_chain(session: Session, *, sender: str = SENDER, nonce: int = 188) -> None:
    session.add(Account(chain_id=CHAIN, address=sender, balance=100_000_000, nonce=nonce))
    session.commit()


def _seed_rejected_occupants(
    session: Session,
    mempool: InMemoryMempool | DatabaseMempool,
    *,
    sender: str = SENDER,
    explicit_hashes: bool = False,
) -> list[str]:
    """Park two apply-rejected withdraw envelopes (nonce 188/189) in the
    mempool and give each a durable ``rejected`` Transaction row — the exact
    shape a follower holds after consensus refused the resubmission.

    ``explicit_hashes`` stores identities that do NOT equal
    ``compute_tx_hash(content)`` — the shape bridge/rollback admissions
    produce via ``mempool.add(tx_hash=...)`` — so the nonce view must match
    on the persisted ``entry.tx_hash``, never a recomputed one.
    """
    hashes: list[str] = []
    for nonce, stake_id in ((188, STAKE_ID), (189, "liq_dead_189")):
        content = _withdraw_tx(sender, nonce, stake_id)
        tx_hash = f"0x{nonce:064x}" if explicit_hashes else compute_tx_hash(content)
        mempool.add(dict(content), chain_id=CHAIN, tx_hash=tx_hash)
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash=tx_hash,
                block_height=None,
                sender=sender,
                recipient=sender,
                payload=content["payload"],
                type="LIQUIDITY_WITHDRAW",
                value=0,
                fee=DEFAULT_TX_FEE_UNITS,
                nonce=nonce,
                status="rejected",
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        hashes.append(tx_hash)
    session.commit()
    return hashes


class _NodeAdapter:
    """In-process HTTP boundary for the CLI: routes each endpoint at the real
    RPC functions — only the socket is fake."""

    def __init__(self, engine, mempool: InMemoryMempool | DatabaseMempool):
        self.engine = engine
        self.mempool = mempool
        self.posts: list[dict] = []
        self.last_result: dict | None = None

    def __call__(self, base_url="", timeout=None, **kw):
        return self

    def get(self, endpoint, **kw):
        path, _, qs = endpoint.partition("?")
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        chain = params.get("chain_id") or None
        if path.startswith("/rpc/mempool"):
            return _maybe_await(
                txmod.get_mempool(
                    _http_request("GET", path),
                    chain_id=chain,
                    limit=int(params.get("limit", "100")),
                    nonce_view=params.get("nonce_view") == "true",
                )
            )
        if path.startswith("/rpc/account/"):
            address = path.rsplit("/", 1)[-1]
            with Session(self.engine) as session:
                account = session.get(Account, (CHAIN, address))
                return {"nonce": account.nonce if account else 0, "balance": account.balance if account else 0}
        if path.startswith("/rpc/liquidity/stakes/"):
            address = path.rsplit("/", 1)[-1].split("?")[0]
            return {
                "success": True,
                "address": address,
                "stakes": [
                    {
                        "stake_id": STAKE_ID,
                        "pool_id": "main",
                        "amount": 36_000_000,
                        "status": "active",
                    }
                ],
            }
        if path.startswith("/rpc/transaction/"):
            tx_hash = path.rsplit("/", 1)[-1]
            return _maybe_await(txmod.get_transaction(_http_request("GET", path), tx_hash, chain))
        raise AssertionError(f"unexpected GET {endpoint}")

    def post(self, endpoint, json=None, **kw):
        assert endpoint == "/rpc/transaction"
        self.posts.append(json)
        request = TransactionRequest.model_validate(json)
        self.last_result = _maybe_await(txmod.submit_transaction(_http_request("POST", endpoint), request))
        return self.last_result


@pytest.fixture(params=["memory", "db"])
def chain_env(monkeypatch, tmp_path, request):
    """Isolated engine + mempool (in-memory and the live DB backend) + patched
    session_scope/mempool singleton. The DB backend gets its own sqlite file
    under tmp_path — never the deployment mempool database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    mempool: InMemoryMempool | DatabaseMempool = (
        InMemoryMempool(chain_id=CHAIN)
        if request.param == "memory"
        else DatabaseMempool(f"sqlite:///{tmp_path / 'mempool.db'}", min_fee=0)
    )

    @contextmanager
    def _session_scope(*_args, **_kwargs):
        with Session(engine) as session:
            yield session

    import aitbc_chain.database as chain_database
    import aitbc_chain.mempool as mempool_module

    monkeypatch.setattr(txmod, "session_scope", _session_scope)
    # ``_sealed_on_chain_tx_hashes`` resolves ``aitbc_chain.database.session_scope``
    # lazily inside the admission critical section — point it at the fixture
    # chain DB so the DB backend's duplicate/sealed lookup never touches the
    # deployment database.
    monkeypatch.setattr(chain_database, "session_scope", _session_scope)
    monkeypatch.setattr(mempool_module, "get_mempool", lambda: mempool)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "supported_chains", CHAIN)
    monkeypatch.setattr(settings, "state_transition_v30_height", 1)
    monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "")
    adapter = _NodeAdapter(engine, mempool)
    return engine, mempool, adapter


def _seed_stake_and_funds(session: Session, sender: str = SENDER, stake_id: str = STAKE_ID) -> None:
    _seed_active_stake(session, sender, stake_id=stake_id)
    _fund_pool_account(session, pool_main_address(), 40_000_000)
    _fund_pool_account(session, pool_treasury_address(), 40_000_000)


def _run_unstake(runner, adapter, wallet_file, monkeypatch, *extra):
    from aitbc_cli.commands.wallet import staking as staking_mod

    monkeypatch.setattr(staking_mod, "AITBCHTTPClient", adapter)
    return runner.invoke(
        staking_mod.wallet,
        [
            "liquidity-unstake",
            "--stake-id",
            STAKE_ID,
            "--wallet-name",
            "w2745",
            "--wallet-path",
            str(wallet_file),
            "--rpc-url",
            "http://node.test",
            "--chain-id",
            CHAIN,
            *extra,
        ],
        obj={"output_format": "json"},
    )


def _write_wallet(tmp_path, sender: str = SENDER) -> Path:
    wallet_file = tmp_path / "w2745.json"
    wallet_file.write_text(json.dumps({"address": sender, "private_key": "0x" + PK_HEX}))
    wallet_file.chmod(0o600)
    return wallet_file


def test_nonce_view_excludes_rejected_occupants_but_legacy_lists_them(chain_env):
    """Opt-in view frees the dead slots; the default listing is unchanged."""
    engine, mempool, _adapter = chain_env
    with Session(engine) as session:
        _seed_chain(session)
        # Stored identities deliberately differ from compute_tx_hash(content):
        # only entry.tx_hash can match the durable rejected rows.
        _seed_rejected_occupants(session, mempool, explicit_hashes=True)

    legacy = _maybe_await(txmod.get_mempool(_http_request("GET", "/rpc/mempool"), chain_id=CHAIN, limit=100))
    assert legacy["success"] is True
    assert {tx["nonce"] for tx in legacy["transactions"]} == {188, 189}

    view = _maybe_await(
        txmod.get_mempool(
            _http_request("GET", "/rpc/mempool"),
            chain_id=CHAIN,
            limit=100,
            nonce_view=True,
        )
    )
    assert view["success"] is True
    assert view["nonce_view_complete"] is True
    assert view["transactions"] == []
    assert view["count"] == 0

    # Bounded read: limit=1 fetches 2 rows, proves truncation and must answer
    # "cannot classify"; limit=2 sees both rows and still classifies them all.
    truncated = _maybe_await(
        txmod.get_mempool(
            _http_request("GET", "/rpc/mempool"),
            chain_id=CHAIN,
            limit=1,
            nonce_view=True,
        )
    )
    assert truncated["success"] is False
    assert truncated["nonce_view_complete"] is False

    exact = _maybe_await(
        txmod.get_mempool(
            _http_request("GET", "/rpc/mempool"),
            chain_id=CHAIN,
            limit=2,
            nonce_view=True,
        )
    )
    assert exact["success"] is True
    assert exact["nonce_view_complete"] is True
    assert exact["transactions"] == []
    assert exact["count"] == 0


def test_nonce_view_genuine_pending_still_occupies(chain_env):
    """Counter-case: a live pending 188 with no rejected row still blocks the
    slot; only the hash-matched rejected 189 is excluded — floor lands on 189.
    Both the shared (non-strict) and the retry-strict helper must agree."""
    engine, mempool, adapter = chain_env
    with Session(engine) as session:
        _seed_chain(session)
        live = _withdraw_tx(SENDER, 188, "liq_live_188")
        live_hash = compute_tx_hash(live)
        mempool.add(dict(live), chain_id=CHAIN, tx_hash=live_hash)
        dead = _withdraw_tx(SENDER, 189, "liq_dead_189")
        dead_hash = compute_tx_hash(dead)
        mempool.add(dict(dead), chain_id=CHAIN, tx_hash=dead_hash)
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash=dead_hash,
                block_height=None,
                sender=SENDER,
                recipient=SENDER,
                payload=dead["payload"],
                type="LIQUIDITY_WITHDRAW",
                value=0,
                fee=DEFAULT_TX_FEE_UNITS,
                nonce=189,
                status="rejected",
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        session.commit()

    from aitbc_cli.utils.nonce import pending_nonce_floor

    assert pending_nonce_floor(adapter, SENDER, 188, CHAIN) == 189
    assert pending_nonce_floor(adapter, SENDER, 188, CHAIN, require_nonce_view=True) == 189


def test_retry_rejected_unstake_signs_attempt_and_seals(chain_env, tmp_path, monkeypatch):
    """Full path: CLI --retry-rejected → nonce view → real sign → real admit
    (dead occupant evicted) → real proposer stages → confirmed at height 1."""
    engine, mempool, adapter = chain_env
    with Session(engine) as session:
        _seed_chain(session)
        _seed_stake_and_funds(session)
        rejected_hashes = set(_seed_rejected_occupants(session, mempool))

    wallet_file = _write_wallet(tmp_path)
    runner = CliRunner()
    result = _run_unstake(runner, adapter, wallet_file, monkeypatch, "--retry-rejected")
    assert result.exit_code == 0, result.output
    assert adapter.last_result is not None and adapter.last_result.get("success") is True

    # Exactly one POST, carrying the attempt-tagged envelope at the freed nonce.
    assert len(adapter.posts) == 1
    posted = adapter.posts[0]
    assert posted["nonce"] == 188
    assert posted["type"] == "LIQUIDITY_WITHDRAW"
    assert posted["payload"]["pool_id"] == "main"
    assert posted["payload"]["stake_id"] == STAKE_ID
    assert posted["payload"]["amount"] == 36_000_000
    assert posted["payload"]["to"] == SENDER
    assert isinstance(posted["payload"]["attempt_id"], str) and len(posted["payload"]["attempt_id"]) == 32

    # Everything but the fresh attempt id is byte-identical to the parked,
    # chain-rejected 188 envelope — same fee, same payload fields.
    old_content = _withdraw_tx(SENDER, 188, STAKE_ID)
    assert compute_tx_hash(old_content) in rejected_hashes
    assert posted["fee"] == old_content["fee"]
    assert {k: v for k, v in posted["payload"].items() if k != "attempt_id"} == old_content["payload"]

    # The signature is real and covers the attempt id.
    normalized_posted = normalize_transaction_data(dict(posted), CHAIN)
    assert verify_transaction_signature(normalized_posted, posted["signature"], SENDER)
    tampered = {
        **normalized_posted,
        "payload": {**normalized_posted["payload"], "attempt_id": "b" * 32},
    }
    assert not verify_transaction_signature(tampered, posted["signature"], SENDER)

    # The node-reported hash is the one parked in the real mempool — distinct
    # from the rejected original (fresh attempt_id ⇒ fresh hash).
    new_hash = adapter.last_result["transaction_hash"]
    assert new_hash != compute_tx_hash(old_content)
    assert new_hash not in rejected_hashes
    assert new_hash in set(mempool.pending_tx_hashes(CHAIN)), "admission must park the new envelope"

    next_height = _seal_only(engine, mempool, new_hash)

    with Session(engine) as session:
        sealed = session.exec(select(Block).where(Block.chain_id == CHAIN)).all()
        assert [b.height for b in sealed] == [next_height]
        record = session.exec(select(Transaction).where(Transaction.chain_id == CHAIN, Transaction.tx_hash == new_hash)).one()
        assert record.status == "confirmed"
        assert record.block_height == next_height
        account = session.get(Account, (CHAIN, SENDER))
        assert account.nonce == 189
        stake = session.get(LiquidityStake, (STAKE_ID, CHAIN))
        assert stake.status == "withdrawn"
        for dead_hash in rejected_hashes:
            dead = session.exec(
                select(Transaction).where(Transaction.chain_id == CHAIN, Transaction.tx_hash == dead_hash)
            ).one()
            assert dead.status == "rejected"


def test_ordinary_transfer_still_seals_at_188_with_rejected_occupants(chain_env):
    """Separate fixture: the shared account-wide allocator — not just the
    strict retry path — sees the freed slot, so an ordinary TRANSFER signs
    nonce 188, is admitted through the same real eviction path and seals.
    attempt_id is not required for the dead-slot release."""
    engine, mempool, adapter = chain_env
    with Session(engine) as session:
        _seed_chain(session)
        rejected_hashes = set(_seed_rejected_occupants(session, mempool))

    from aitbc_cli.utils.nonce import next_send_nonce

    nonce = next_send_nonce(adapter, SENDER, CHAIN)
    assert nonce == 188, "classified view must free the rejected occupants for ordinary sends too"

    tx = {
        "type": "TRANSFER",
        "from": SENDER,
        "to": OTHER_SENDER,
        "chain_id": CHAIN,
        "amount": 1,
        "nonce": nonce,
        "fee": 100,
        # TransactionRequest fills payload.to/amount when absent — signing
        # the pre-injection envelope would fail verification, so the payload
        # carries them up front exactly like the withdraw fixtures do.
        "payload": {"to": OTHER_SENDER, "amount": 1},
    }
    tx["signature"] = sign_transaction_data(tx, PK_HEX)
    normalized = normalize_transaction_data(tx, CHAIN)
    result = _maybe_await(
        txmod.submit_transaction(
            _http_request("POST", "/rpc/transaction"),
            TransactionRequest.model_validate(normalized),
        )
    )
    assert result["success"] is True
    new_hash = result["transaction_hash"]
    assert new_hash not in rejected_hashes
    assert new_hash in set(mempool.pending_tx_hashes(CHAIN))

    # Sealing the ordinary tx needs an OTHER_SENDER account only as recipient
    # materialization — v22+ creates it on apply; sender is funded already.
    next_height = _seal_only(engine, mempool, new_hash)

    with Session(engine) as session:
        record = session.exec(select(Transaction).where(Transaction.chain_id == CHAIN, Transaction.tx_hash == new_hash)).one()
        assert record.status == "confirmed"
        assert record.block_height == next_height
        account = session.get(Account, (CHAIN, SENDER))
        assert account.nonce == 189


def test_nonce_view_lookup_failure_is_explicit_incomplete(chain_env, monkeypatch, tmp_path):
    """A DB failure inside classification must answer 'cannot classify',
    never an empty-but-complete view — and the real ``--retry-rejected``
    command must abort before signing or POSTing anything."""
    engine, mempool, adapter = chain_env
    with Session(engine) as session:
        _seed_chain(session)
        _seed_stake_and_funds(session)
        _seed_rejected_occupants(session, mempool)

    @contextmanager
    def _broken_scope(*_args, **_kwargs):
        raise RuntimeError("db gone")
        yield  # pragma: no cover

    monkeypatch.setattr(txmod, "session_scope", _broken_scope)
    view = _maybe_await(
        txmod.get_mempool(
            _http_request("GET", "/rpc/mempool"),
            chain_id=CHAIN,
            limit=100,
            nonce_view=True,
        )
    )
    assert view == {"success": False, "nonce_view_complete": False, "transactions": [], "count": 0}

    from aitbc_cli.commands.wallet import staking as staking_mod

    sign = Mock()
    monkeypatch.setattr(staking_mod, "_sign_transaction", sign)
    wallet_file = _write_wallet(tmp_path)
    runner = CliRunner()
    result = _run_unstake(runner, adapter, wallet_file, monkeypatch, "--retry-rejected")
    # ``_LIQUIDITY_TX_ERRORS`` catches the RuntimeError subclass, prints the
    # classification reason and exits 1 — nonzero exit, nothing signed, nothing POSTed.
    assert result.exit_code != 0
    assert "Could not classify" in result.output
    sign.assert_not_called()
    assert adapter.posts == []


def _session_factory_for(engine):
    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session

    return factory


def _seal_only(engine, mempool: InMemoryMempool | DatabaseMempool, expected_hash: str) -> int:
    """Seal ``expected_hash`` through the real proposer stages and return the height.

    Exercises ``_collect_proposal_txs`` (real mempool drain), ``_process_proposal_txs``
    (real ``apply_transaction`` including signature verification), ``_assemble_proposal_block``
    (real state root), ``_sign_block_hash_for`` (real consensus signature) and
    ``_commit_and_record_block`` (real commit). ``_propose_block`` itself is not
    run, so its per-block ``reset_processed_cache`` on the shared state
    transition is replicated explicitly before collection — without it a prior
    test's applied hashes would falsely replay. Also not exercised:
    ``_resolve_proposal_head`` (fixed test parent), round-proposer
    selection, PBFT/attestation gates and network broadcast — a
    component-level seal, not a fleet seal.
    """
    proposer = PoAProposer(
        config=ProposerConfig(
            chain_id=CHAIN,
            proposer_id=SENDER,
            interval_seconds=1,
            max_block_size_bytes=1_000_000,
            max_txs_per_block=100,
        ),
        session_factory=_session_factory_for(engine),
    )
    proposer._validator_keys = {SENDER: PK_HEX}
    next_height = 1
    parent_hash = "0x00"  # Fixed test parent; head resolution is not exercised.
    with Session(engine) as session:
        timestamp = datetime.now(UTC)
        get_state_transition().reset_processed_cache()
        pending_txs, account_map, existing_tx_map, _reserved, _stale = proposer._collect_proposal_txs(
            session, mempool, block_version=30
        )
        assert expected_hash in {tx.tx_hash for tx in pending_txs}
        processed_txs, _changed, ok = proposer._process_proposal_txs(
            session, pending_txs, account_map, existing_tx_map, next_height, timestamp
        )
        assert ok
        assert [tx.tx_hash for tx in processed_txs] == [expected_hash]
        block, _block_hash = proposer._assemble_proposal_block(
            session, next_height, parent_hash, timestamp, processed_txs, SENDER
        )
        block.signature = proposer._sign_block_hash_for(SENDER, block)
        assert block.signature, "real proposer signing must produce a signature"
        assert proposer._commit_and_record_block(session, block, SENDER, None, timestamp) is True
        session.commit()
    return next_height
