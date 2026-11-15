"""#1940 F4 — isolated full post-state attestation verification.

Covers the dormant ``attestation_post_state_height`` gate: the probe must
reproduce claimed state/aux/bridge roots by re-executing the request's
transactions on a consistent SQLite snapshot of local parent state through
the real importer — while never touching production state, caches,
counters, or the source connection.
"""

from __future__ import annotations

import asyncio
import copy
import json
import shutil
import sqlite3
import threading
import time
from types import SimpleNamespace
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path

import pytest
from aitbc.crypto.consensus_signing import sign_block_hash
from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain import database as db_module
from aitbc_chain import mempool as mempool_module
from aitbc_chain.base_models import Account, Block, ValidatorDeactivation
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.config import settings
from aitbc_chain.consensus import attestation_state_probe as probe_mod
from aitbc_chain.consensus.attestation_state_probe import (
    _AttestationProbeImporter,
    post_state_probe_active,
    probe_post_state,
)
from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.remote_attestation_v9 import _int_header_height
from aitbc_chain.mempool import compute_tx_hash
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.state import block_deltas, side_root_shadow, state_transition_apply
from aitbc_chain.state.gpu_resources import GPURegistration
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import StateTransition, get_block_version_for_height
from sqlalchemy import text
from sqlmodel import Session, create_engine, select

CHAIN = "probe-1940"
HEIGHT = 10
PARENT_HEIGHT = 9
T0 = datetime(2026, 1, 1, tzinfo=UTC)
TS = "2026-01-01T00:00:00+00:00"
PARENT_HASH = "0x" + "aa" * 32
ZERO_HASH = "0x" + "00" * 32

SENDER_KEY = "0x" + "11" * 32
RECIPIENT_KEY = "0x" + "22" * 32
SENDER = derive_ethereum_address(SENDER_KEY)
RECIPIENT = derive_ethereum_address(RECIPIENT_KEY)
PROPOSER = "0x" + "33" * 20


# --------------------------------------------------------------------------
# fixtures / builders (real signatures, real apply)
# --------------------------------------------------------------------------


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=SENDER, balance=1_000_000, nonce=0))
        session.add(Account(chain_id=CHAIN, address=RECIPIENT, balance=0, nonce=0))
        session.add(
            Block(
                chain_id=CHAIN,
                height=PARENT_HEIGHT,
                hash=PARENT_HASH,
                parent_hash=ZERO_HASH,
                proposer=PROPOSER,
                timestamp=T0,
                tx_count=0,
            )
        )
        session.commit()

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    factory.db_path = tmp_path / "chain.db"  # type: ignore[attr-defined]
    factory.engine = engine  # type: ignore[attr-defined]
    return factory


@pytest.fixture(autouse=True)
def _gate(monkeypatch):
    monkeypatch.setattr(settings, "attestation_post_state_height", HEIGHT)
    monkeypatch.setattr(settings, "attestation_post_state_timeout_seconds", 10.0)
    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", False)
    monkeypatch.setattr(settings, "validator_set", "")
    monkeypatch.setattr(settings, "attest_lag_wait_enabled", False)
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _hash(*parts: object) -> str:
    import hashlib

    return "0x" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _sign_data(private_key: str, data: dict) -> str:
    from eth_utils import keccak

    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def _attach_sender_sig(tx: dict, private_key: str) -> dict:
    signable = {k: v for k, v in tx.items() if k != "signature"}
    if "amount" in signable:
        signable.pop("value", None)
    tx["signature"] = _sign_data(private_key, signable)
    return tx


def _tx(value: int = 5000, nonce: int = 0) -> dict:
    return _attach_sender_sig(
        {
            "from": SENDER,
            "to": RECIPIENT,
            "amount": value,
            "value": value,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": nonce,
            "type": "TRANSFER",
            "chain_id": CHAIN,
            "payload": {},
        },
        SENDER_KEY,
    )


def _with_tx_hash(tx: dict) -> dict:
    tx = dict(tx)
    tx["tx_hash"] = compute_tx_hash({k: v for k, v in tx.items() if k != "tx_hash"})
    return tx


def _version() -> int:
    from aitbc_chain.state.state_transition import get_block_version_for_height

    return get_block_version_for_height(HEIGHT)


def _apply_on_clone(session_factory, block_data: dict, txs: list[dict], version: int):
    """Run the real importer on a file copy; return (state_root, aux, bridge)."""
    src = Path(session_factory.db_path)
    clone = src.with_name(src.name + ".clone")
    shutil.copy(src, clone)
    engine = create_engine(f"sqlite:///{clone}")
    try:
        with Session(engine) as session:
            importer = _AttestationProbeImporter(CHAIN, session)
            bd = dict(block_data)
            bd["hash"] = bd.get("hash") or _hash("clone-block", bd.get("height"))
            bd["state_root"] = "0x" + "00" * 32
            bd["aux_state_root"] = None
            bd["bridge_state_root"] = None
            bd["block_metadata"] = json.dumps({"state_transition_version": version})
            # The clone apply exists only to compute the expected roots;
            # the MV proposer-schedule gate is an acceptance check
            # orthogonal to state transition and must not block root
            # computation for negative schedule/signature cases. The probe
            # itself still runs the full MV check on the scratch session.
            mv_enabled = settings.multi_validator_consensus_enabled
            settings.multi_validator_consensus_enabled = False
            try:
                result = importer._append_block(
                    session,
                    bd,
                    copy.deepcopy(txs),
                    skip_state_root_validation=True,
                    _state_transition=StateTransition(),
                )
            finally:
                settings.multi_validator_consensus_enabled = mv_enabled
            assert result.accepted, result.reason
            session.commit()
            root = compute_state_root_full(session, CHAIN)
            aux = ""
            if version >= 14:
                aux = side_root_shadow.committed_fingerprint(session.connection().connection, version)["fingerprint"]
            derive_data = dict(bd)
            derive_data["bridge_state_root"] = None
            bridge = importer._derive_bridge_state_root(session, derive_data, copy.deepcopy(txs))
            return root or "", aux, bridge
    finally:
        engine.dispose()


def _request(
    session_factory,
    txs: list[dict],
    *,
    state_root=None,
    aux_state_root=None,
    bridge_state_root=None,
    height=HEIGHT,
    parent_hash=PARENT_HASH,
    timestamp=TS,
    block_metadata=None,
    proposer_sig="0x" + "44" * 65,
    proposer=PROPOSER,
    embedded_sig="",
):
    """Build a well-formed attest request whose claimed roots reproduce."""
    version = _version()
    tx_hashes = [str(tx.get("tx_hash") or compute_tx_hash({k: v for k, v in tx.items() if k != "tx_hash"})) for tx in txs]
    base = {
        "chain_id": CHAIN,
        "height": height,
        "parent_hash": parent_hash,
        "proposer": proposer,
        "timestamp": timestamp,
        "tx_count": len(txs),
        "tx_hashes": tx_hashes,
        "state_root": state_root,
        "aux_state_root": aux_state_root,
        "bridge_state_root": bridge_state_root,
        "block_metadata": block_metadata,
    }
    if state_root is None or aux_state_root is None or bridge_state_root is None:
        root, aux, bridge = _apply_on_clone(session_factory, base, txs, version)
        base["state_root"] = state_root if state_root is not None else root
        base["aux_state_root"] = aux_state_root if aux_state_root is not None else (aux or None)
        base["bridge_state_root"] = bridge_state_root if bridge_state_root is not None else bridge
    base["hash"] = compute_block_hash(
        CHAIN,
        height,
        parent_hash,
        timestamp,
        tx_hashes,
        proposer,
        str(base["state_root"] or ""),
        str(base["bridge_state_root"] or ""),
        str(base["aux_state_root"] or ""),
    )
    header = dict(base)
    header["signature"] = embedded_sig
    return header, txs, proposer_sig


def _probe(session_factory, header, txs, **kw):
    with session_factory() as session:
        return probe_post_state(session, CHAIN, header, txs, deadline=kw.pop("deadline", None), **kw)


def _svc(session_factory) -> RemoteAttestationService:
    return RemoteAttestationService(CHAIN, {}, session_factory=session_factory)


# --------------------------------------------------------------------------
# gate predicate
# --------------------------------------------------------------------------


class TestGatePredicate:
    def test_unset_and_prethreshold_inactive(self, monkeypatch):
        monkeypatch.setattr(settings, "attestation_post_state_height", None)
        assert not post_state_probe_active(HEIGHT)
        monkeypatch.setattr(settings, "attestation_post_state_height", HEIGHT + 1)
        assert not post_state_probe_active(HEIGHT)
        assert post_state_probe_active(HEIGHT + 1)

    @pytest.mark.parametrize("bad", [None, True, -1, "10", 10.0])
    def test_malformed_threshold_inactive(self, monkeypatch, bad):
        monkeypatch.setattr(settings, "attestation_post_state_height", bad)
        assert not post_state_probe_active(HEIGHT)

    @pytest.mark.parametrize("bad_height", [None, True, -1, "10", 10.0])
    def test_malformed_height_inactive(self, bad_height):
        assert not post_state_probe_active(bad_height)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# probe_post_state — fresh apply path
# --------------------------------------------------------------------------


class TestProbeFreshApply:
    def test_valid_post_state_accepted(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None

    def test_tampered_state_root_refused(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs, state_root="0x" + "ff" * 32)
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "post_state_apply_refused"

    def test_overspend_tx_with_matching_roots_accepted(self, session_factory):
        """A legitimately failed tx is fine when claimed roots still match —
        the probe must not blanket-forbid failed transactions."""
        txs = [_with_tx_hash(_tx(value=700_000))]
        header, txs, sig = _request(session_factory, txs)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None

    @pytest.mark.parametrize(
        "mutate,reason",
        [
            (lambda h: h.update(height="10"), "post_state_bad_height"),
            (lambda h: h.update(height=True), "post_state_bad_height"),
            (lambda h: h.update(height=-1), "post_state_bad_height"),
            (lambda h: h.update(timestamp="not-a-time"), "post_state_bad_timestamp"),
            (lambda h: h.update(timestamp=None), "post_state_bad_timestamp"),
            (lambda h: h.update(state_root="0x1234"), "post_state_bad_state_root"),
            (lambda h: h.update(state_root=None), "post_state_bad_state_root"),
        ],
    )
    def test_malformed_header_refused_before_apply(self, session_factory, mutate, reason):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        mutate(header)
        assert _probe(session_factory, header, txs, proposer_signature=sig) == reason

    def test_rival_tip_refused(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        with session_factory() as session:
            session.add(
                Block(
                    chain_id=CHAIN,
                    height=HEIGHT,
                    hash="0x" + "bb" * 32,
                    parent_hash=PARENT_HASH,
                    proposer=PROPOSER,
                    timestamp=T0,
                    tx_count=0,
                )
            )
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "not_at_parent"

    def test_ahead_tip_refused(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        with session_factory() as session:
            session.add(
                Block(
                    chain_id=CHAIN,
                    height=HEIGHT + 1,
                    hash="0x" + "cc" * 32,
                    parent_hash=PARENT_HASH,
                    proposer=PROPOSER,
                    timestamp=T0,
                    tx_count=0,
                )
            )
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "not_at_parent"

    def test_no_input_mutation(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        header_before = copy.deepcopy(header)
        txs_before = copy.deepcopy(txs)
        _probe(session_factory, header, txs, proposer_signature=sig)
        assert header == header_before
        assert txs == txs_before

    def test_source_connection_read_only(self, session_factory):
        """The probe only reads the source DB — the exact source Session and
        raw sqlite connection stay open across the direct probe call and
        ``total_changes`` (the write counter) must not move."""
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        with session_factory() as session:
            raw = session.connection().connection.dbapi_connection
            before = raw.total_changes
            accounts_before = {
                a.address: (a.balance, a.nonce) for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()
            }
            block_count = len(session.exec(select(Block).where(Block.chain_id == CHAIN)).all())
            verdict = probe_post_state(session, CHAIN, header, txs, deadline=time.monotonic() + 10, proposer_signature=sig)
            assert verdict is None
            assert raw.total_changes == before
            accounts_after = {
                a.address: (a.balance, a.nonce) for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()
            }
            assert accounts_after == accounts_before
            assert len(session.exec(select(Block).where(Block.chain_id == CHAIN)).all()) == block_count

    def test_prune_watermark_untouched(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        block_deltas._last_pruned_height[CHAIN] = 4242
        try:
            _probe(session_factory, header, txs, proposer_signature=sig)
            assert block_deltas._last_pruned_height[CHAIN] == 4242
        finally:
            block_deltas._last_pruned_height.pop(CHAIN, None)

    def test_sync_rejection_counters_unpolluted(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs, state_root="0x" + "ff" * 32)
        before = {
            name: metrics_registry._counters.get(name)  # type: ignore[attr-defined]
            for name in ("sync_blocks_rejected_total", "sync_state_root_rejected_total")
        }
        _probe(session_factory, header, txs, proposer_signature=sig)
        for name, val in before.items():
            assert metrics_registry._counters.get(name) == val  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# probe_post_state — already-imported path
# --------------------------------------------------------------------------


class TestProbeAlreadyImported:
    def _import_block(self, session_factory, header, txs):
        """Really import the block on the source DB, then re-probe it."""
        with session_factory() as session:
            importer = _AttestationProbeImporter(CHAIN, session)
            bd = dict(header)
            bd["signature"] = ""
            result = importer._append_block(session, bd, copy.deepcopy(txs), _state_transition=StateTransition())
            assert result.accepted, result.reason

    def test_imported_block_reverifies(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        self._import_block(session_factory, header, txs)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None

    def test_stored_root_corruption_refused(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        self._import_block(session_factory, header, txs)
        with session_factory() as session:
            block = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == HEIGHT)).one()
            block.state_root = "0x" + "ff" * 32
            session.add(block)
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "post_state_root_mismatch"

    def test_request_root_diverging_from_stored_refused(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        self._import_block(session_factory, header, txs)
        forged = dict(header, state_root="0x" + "ee" * 32)
        # hash intentionally left as the imported block's — upstream hash
        # binding is the v9 check's job; the probe must still bind the
        # carried root fields to the stored row.
        assert _probe(session_factory, forged, txs, proposer_signature=sig) == "post_state_root_mismatch"


# --------------------------------------------------------------------------
# aux root (v14+)
# --------------------------------------------------------------------------


class TestProbeAuxRoot:
    def test_missing_aux_refused_at_v14(self, session_factory, monkeypatch):
        monkeypatch.setattr(probe_mod, "get_block_version_for_height", lambda h: 14)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        header["aux_state_root"] = None
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "post_state_missing_aux_root"

    def test_wrong_aux_refused_at_v18(self, session_factory, monkeypatch):
        """v14/v15-era committed sets include node-local volatile tables so
        the importer runs aux compare-only there; the rejecting check lives
        at v18+ where the set is fully verifiable."""
        monkeypatch.setattr(probe_mod, "get_block_version_for_height", lambda h: 18)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        root, aux, bridge = _apply_on_clone(session_factory, header, txs, 18)
        header["aux_state_root"] = "0x" + "ab" * 32
        header["state_root"] = root
        header["bridge_state_root"] = bridge
        header["hash"] = compute_block_hash(
            CHAIN,
            HEIGHT,
            PARENT_HASH,
            TS,
            header["tx_hashes"],
            PROPOSER,
            root,
            bridge,
            header["aux_state_root"],
        )
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "post_state_apply_refused"

    def test_correct_aux_accepted_at_v14(self, session_factory, monkeypatch):
        monkeypatch.setattr(probe_mod, "get_block_version_for_height", lambda h: 14)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        # _request already computed aux at the real version; recompute at 14.
        root, aux, bridge = _apply_on_clone(session_factory, header, txs, 14)
        header["aux_state_root"] = aux
        header["state_root"] = root
        header["bridge_state_root"] = bridge
        header["hash"] = compute_block_hash(
            CHAIN,
            HEIGHT,
            PARENT_HASH,
            TS,
            header["tx_hashes"],
            PROPOSER,
            root,
            bridge,
            aux,
        )
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None


# --------------------------------------------------------------------------
# version pinning — peer metadata cannot downgrade apply rules
# --------------------------------------------------------------------------


class TestVersionPinning:
    def test_peer_downgrade_metadata_ignored(self, session_factory, monkeypatch):
        """A peer-stamped state_transition_version must not pick apply rules:
        the probe pins the height-derived version into scratch metadata."""
        seen = {}

        from aitbc_chain.sync_block_import import BlockImportMixin

        orig = BlockImportMixin._append_block

        def spy(self, session, block_data, transactions=None, **kw):
            seen["metadata"] = block_data.get("block_metadata")
            return orig(self, session, block_data, transactions, **kw)

        monkeypatch.setattr(BlockImportMixin, "_append_block", spy)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs, block_metadata=json.dumps({"state_transition_version": 1}))
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None
        stamped = json.loads(seen["metadata"])
        assert stamped["state_transition_version"] == _version()


# --------------------------------------------------------------------------
# v9 / _run_v9_check integration (real session factory, real threads)
# --------------------------------------------------------------------------


class TestV9Integration:
    @pytest.mark.asyncio
    async def test_probe_refusal_flows_through_run_v9(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs, state_root="0x" + "ff" * 32)
        svc = _svc(session_factory)
        verdict = await svc._run_v9_check(header, txs, proposer_signature=sig)
        assert verdict == "post_state_apply_refused"

    @pytest.mark.asyncio
    async def test_probe_accept_returns_none(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        svc = _svc(session_factory)
        assert await svc._run_v9_check(header, txs, proposer_signature=sig) is None

    @pytest.mark.asyncio
    async def test_string_height_cannot_bypass(self, session_factory):
        """height="10" is int-convertible so the gate arms, but the probe's
        strict-int contract refuses — a malformed numeric cannot skip it."""
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        header["height"] = "10"
        svc = _svc(session_factory)
        verdict = await svc._run_v9_check(header, txs, proposer_signature=sig)
        assert verdict == "post_state_bad_height"

    @pytest.mark.asyncio
    async def test_gate_inactive_never_calls_probe(self, session_factory, monkeypatch):
        monkeypatch.setattr(settings, "attestation_post_state_height", None)
        called = []

        def boom(*a, **kw):
            called.append(1)
            raise AssertionError("probe must not run when gate is unset")

        monkeypatch.setattr(probe_mod, "probe_post_state", boom)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        svc = _svc(session_factory)
        # shallow path: parent is at height-1 -> None verdict without probe
        assert await svc._run_v9_check(header, txs) is None
        assert not called

    @pytest.mark.asyncio
    async def test_probe_busy_single_flight(self, session_factory):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        svc = _svc(session_factory)
        svc._attest_probe_lock.acquire()
        try:
            verdict = await svc._run_post_state_probe(header, txs, sig)
            assert verdict == "post_state_busy"
        finally:
            svc._attest_probe_lock.release()
        # permit released by owner only — a fresh probe now runs
        assert await svc._run_post_state_probe(header, txs, sig) is None

    @pytest.mark.asyncio
    async def test_probe_timeout_refuses(self, session_factory, monkeypatch):
        monkeypatch.setattr(settings, "attestation_post_state_timeout_seconds", 0.05)
        real = probe_mod.probe_post_state

        def _slow(*a, **kw):
            time.sleep(0.4)
            return None

        monkeypatch.setattr(probe_mod, "probe_post_state", _slow)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        svc = _svc(session_factory)
        verdict = await svc._run_v9_check(header, txs, proposer_signature=sig)
        assert verdict == "post_state_timeout"
        # The worker keeps its permit until it actually finishes — restore
        # the real probe once the slow worker has drained, then a fresh
        # probe is not stuck busy.
        probe_mod.probe_post_state = real
        await asyncio.sleep(0.6)
        assert await svc._run_post_state_probe(header, txs, sig) is None

    @pytest.mark.asyncio
    async def test_request_signature_reaches_probe(self, session_factory, monkeypatch):
        seen = {}

        real = probe_mod.probe_post_state

        def spy(session, chain_id, header, txs, **kw):
            seen.update(kw)
            return real(session, chain_id, header, txs, **kw)

        monkeypatch.setattr(probe_mod, "probe_post_state", spy)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        svc = _svc(session_factory)
        assert await svc._run_v9_check(header, txs, proposer_signature=sig) is None
        assert seen.get("proposer_signature") == sig

    @pytest.mark.asyncio
    async def test_probe_runs_on_worker_thread(self, session_factory, monkeypatch):
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        svc = _svc(session_factory)
        seen = {}
        real = probe_mod.probe_post_state

        def spy(*a, **kw):
            seen["thread"] = threading.get_ident()
            return real(*a, **kw)

        # probe_post_state is imported inside the check from the module —
        # patching the module attribute is what the call resolves.
        monkeypatch.setattr(probe_mod, "probe_post_state", spy)
        verdict = await svc._run_v9_check(header, txs, proposer_signature=sig)
        assert verdict is None
        assert seen["thread"] != threading.get_ident()


# --------------------------------------------------------------------------
# MultiValidatorPoA chain-state session factory
# --------------------------------------------------------------------------


class TestMVSessionFactory:
    def test_factory_routes_chain_state_reads(self, session_factory, monkeypatch):
        monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True)
        monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": PROPOSER, "stake": "1000"}]))
        probe_session = Session(session_factory.engine)
        try:
            mv = MultiValidatorPoA.from_settings(CHAIN, chain_state_session_factory=lambda: nullcontext(probe_session))
            # _current_head_height reads through the injected factory — the
            # scratch/probe session — returning this DB's tip (9).
            assert mv._current_head_height() == PARENT_HEIGHT
        finally:
            probe_session.close()

    def test_default_factory_uses_session_scope(self, monkeypatch):
        monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True)
        monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": PROPOSER, "stake": "1000"}]))
        mv = MultiValidatorPoA.from_settings(CHAIN)
        assert mv._chain_state_session_factory is None


# --------------------------------------------------------------------------
# StateTransition cache policy + module-binding accessor
# --------------------------------------------------------------------------


class TestCachePolicy:
    def test_probe_transition_disables_cache(self):
        st = StateTransition(cache_side_effects=False)
        assert st._apply_cache() is None

    def test_default_transition_uses_module_binding(self):
        st = StateTransition()
        assert st._apply_cache() is state_transition_apply._cache

    def test_accessor_follows_module_patch(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(state_transition_apply, "_cache", sentinel)
        assert StateTransition()._apply_cache() is sentinel
        assert StateTransition(cache_side_effects=False)._apply_cache() is None


# --------------------------------------------------------------------------
# signature contract — the verified request-envelope proposer_signature is
# authoritative; an embedded header signature is only a consistency check
# --------------------------------------------------------------------------


class TestSignaturePolicy:
    def test_missing_request_signature_refused_when_required(self, session_factory, monkeypatch):
        monkeypatch.setattr(settings, "bridge_block_signature_required", True)
        # Independent of the legacy attest-request rollout flag: an absent
        # request signature refuses while post-state mode is armed.
        monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
        txs = [_with_tx_hash(_tx())]
        header, txs, _sig = _request(session_factory, txs)
        for missing in (None, ""):
            assert _probe(session_factory, header, txs, proposer_signature=missing) == "post_state_missing_proposer_signature"

    def test_missing_signature_allowed_under_global_bypass(self, session_factory, monkeypatch):
        """``bridge_block_signature_required=False`` is the explicit legacy
        dev/test override — an absent request signature stays allowed."""
        monkeypatch.setattr(settings, "bridge_block_signature_required", False)
        txs = [_with_tx_hash(_tx())]
        header, txs, _sig = _request(session_factory, txs)
        assert _probe(session_factory, header, txs, proposer_signature=None) is None

    def test_embedded_signature_mismatch_refused(self, session_factory):
        """A truthy embedded header signature differing from the verified
        request-envelope signature refuses — the envelope wins."""
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs, embedded_sig="0x" + "99" * 65)
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "post_state_signature_mismatch"

    def test_embedded_signature_equal_to_request_allowed(self, session_factory):
        """The honest collector omits the field (empty embedded) — a matching
        embedded value is equally acceptable."""
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        header["signature"] = sig
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None

    def test_truthy_embedded_with_missing_request_refused(self, session_factory, monkeypatch):
        """Fail closed: a truthy embedded signature that cannot be
        cross-checked against a request signature refuses even under the
        explicit bypass."""
        monkeypatch.setattr(settings, "bridge_block_signature_required", False)
        txs = [_with_tx_hash(_tx())]
        header, txs, _sig = _request(session_factory, txs, embedded_sig="0x" + "77" * 65)
        assert _probe(session_factory, header, txs, proposer_signature=None) == "post_state_signature_mismatch"


# --------------------------------------------------------------------------
# bridge root — carried, bound to the authenticated header/stored row; never
# re-derived from follower-local service records (deterministic enforcement
# is F5 scope)
# --------------------------------------------------------------------------


class TestBridgeRootCarried:
    def test_unreconstructible_bridge_root_accepted(self, session_factory):
        """Regression for the removed fresh-path re-derivation: the legacy
        importer trusts the carried ``bridge_state_root`` because its
        committed-set digest depends on producer-local service records a
        follower does not have. A correctly hashed request with valid
        account/aux roots and a bridge root no local service record can
        reproduce must NOT spuriously refuse."""
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs, bridge_state_root="0x" + "77" * 32)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None

    def test_imported_bridge_root_binds_request(self, session_factory):
        """Already-imported path: the stored row's bridge root binds to the
        request — divergence refuses. This is stored-row binding, not local
        re-derivation."""
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs, bridge_state_root="0x" + "77" * 32)
        with session_factory() as session:
            importer = _AttestationProbeImporter(CHAIN, session)
            bd = dict(header)
            bd["signature"] = ""
            result = importer._append_block(session, bd, copy.deepcopy(txs), _state_transition=StateTransition())
            assert result.accepted, result.reason
        forged = dict(header, bridge_state_root="0x" + "88" * 32)
        assert _probe(session_factory, forged, txs, proposer_signature=sig) == "post_state_bridge_mismatch"


# --------------------------------------------------------------------------
# MultiValidatorPoA schedule — real proposer keys over the scratch session
# --------------------------------------------------------------------------

MV_KEY_A = "0x" + "44" * 32
MV_KEY_B = "0x" + "55" * 32
MV_ADDR_A = derive_ethereum_address(MV_KEY_A)
MV_ADDR_B = derive_ethereum_address(MV_KEY_B)
MV_KEYS = {MV_ADDR_A: MV_KEY_A, MV_ADDR_B: MV_KEY_B}


def _enable_mv(monkeypatch, *addresses: str) -> None:
    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True)
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": a, "stake": "1000"} for a in addresses]))
    monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
    monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", False)
    # Deterministic correct/wrong-slot coverage: the schedule gate must
    # be explicitly armed, not inherited from the global default.
    monkeypatch.setattr(settings, "consensus_enforce_proposer_schedule", True)


def _scheduled(addresses: tuple[str, ...]) -> str | None:
    """The deterministic schedule winner for (HEIGHT, round 0) — the same
    derivation the probe's MV instance performs on the scratch session."""
    mv = MultiValidatorPoA.from_settings(CHAIN)
    return mv.select_proposer(HEIGHT, 0)


class TestMVRealSignature:
    """Real secp256k1 proposer signatures over the canonical seven-field
    header message — no fake signature constants."""

    def _signed_request(self, session_factory, proposer: str):
        header, txs, _sig = _request(session_factory, [], proposer=proposer)
        # Honest collector projection: signature travels in the request
        # envelope, the header carries no embedded signature.
        sig = sign_block_hash(header, MV_KEYS[proposer])
        return header, txs, sig

    def test_correct_slot_real_signature_accepted(self, session_factory, monkeypatch):
        _enable_mv(monkeypatch, MV_ADDR_A, MV_ADDR_B)
        expected = _scheduled((MV_ADDR_A, MV_ADDR_B))
        assert expected in (MV_ADDR_A, MV_ADDR_B)
        header, txs, sig = self._signed_request(session_factory, expected)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None

    def test_wrong_slot_refused(self, session_factory, monkeypatch):
        _enable_mv(monkeypatch, MV_ADDR_A, MV_ADDR_B)
        expected = _scheduled((MV_ADDR_A, MV_ADDR_B))
        other = MV_ADDR_B if expected == MV_ADDR_A else MV_ADDR_A
        header, txs, sig = self._signed_request(session_factory, other)
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "post_state_apply_refused"

    def test_invalid_signature_refused(self, session_factory, monkeypatch):
        """Correct slot but the signature does not recover to the proposer —
        a real signature over the wrong key still refuses under MV."""
        _enable_mv(monkeypatch, MV_ADDR_A, MV_ADDR_B)
        expected = _scheduled((MV_ADDR_A, MV_ADDR_B))
        wrong_key = MV_KEY_B if expected == MV_ADDR_A else MV_KEY_A
        header, txs, _sig = _request(session_factory, [], proposer=expected)
        sig = sign_block_hash(header, wrong_key)
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "post_state_apply_refused"

    def test_onchain_deactivated_proposer_refused(self, session_factory, monkeypatch):
        _enable_mv(monkeypatch, MV_ADDR_A, MV_ADDR_B)
        expected = _scheduled((MV_ADDR_A, MV_ADDR_B))
        assert expected is not None
        # Arm slashing and seal a deactivation marker at the parent height —
        # the scratch snapshot carries it and the injected session reads it.
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)
        with session_factory() as session:
            session.add(
                ValidatorDeactivation(
                    chain_id=CHAIN,
                    validator_address=canonical_address(expected),
                    block_height=PARENT_HEIGHT,
                )
            )
        header, txs, sig = self._signed_request(session_factory, expected)
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "post_state_apply_refused"

    def test_scratch_reads_never_open_production_scope(self, session_factory, monkeypatch):
        """The probe's MV instance must resolve chain-state reads through the
        injected scratch-session factory — the production ``session_scope``
        is a fail-if-called sentinel here."""
        _enable_mv(monkeypatch, MV_ADDR_A)

        def _boom_scope(*a, **k):
            raise AssertionError("production session_scope opened during probe")

        monkeypatch.setattr(db_module, "session_scope", _boom_scope)
        expected = _scheduled((MV_ADDR_A,))
        assert expected == MV_ADDR_A
        header, txs, sig = self._signed_request(session_factory, MV_ADDR_A)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None

    def test_injected_read_error_refuses(self, session_factory, monkeypatch):
        """An injected scratch-session read failure must refuse — snapshot
        verification cannot waive a check on unreadable state."""
        _enable_mv(monkeypatch, MV_ADDR_A)
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)

        class _BrokenSession:
            def exec(self, *a, **k):
                raise RuntimeError("scratch read failed")

        real_from_settings = MultiValidatorPoA.from_settings

        def _broken_factory(cls, chain_id, **kw):
            kw["chain_state_session_factory"] = lambda: nullcontext(_BrokenSession())
            return real_from_settings(chain_id, **kw)

        monkeypatch.setattr(MultiValidatorPoA, "from_settings", classmethod(_broken_factory))
        header, txs, sig = self._signed_request(session_factory, MV_ADDR_A)
        verdict = _probe(session_factory, header, txs, proposer_signature=sig)
        assert verdict is not None and verdict.startswith("post_state")

    def test_production_session_scope_fallback_unchanged(self, monkeypatch):
        """Without an injected factory the production path keeps its legacy
        degrade-don't-raise fallbacks."""
        monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True)
        monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": MV_ADDR_A, "stake": "1000"}]))
        monkeypatch.setattr(settings, "consensus_chain_slashing_enabled", True)

        class _BrokenSession:
            def exec(self, *a, **k):
                raise RuntimeError("no db in unit test")

        monkeypatch.setattr(db_module, "session_scope", lambda chain_id: nullcontext(_BrokenSession()))
        mv = MultiValidatorPoA.from_settings(CHAIN)
        assert mv._chain_deactivated_addresses(5) == frozenset()
        assert mv._current_head_height() is None


# --------------------------------------------------------------------------
# deadline / resource semantics
# --------------------------------------------------------------------------


class TestDeadlineSemantics:
    def test_expired_deadline_refuses_without_sleep(self, session_factory):
        """An already-expired deadline refuses in-band — deterministic, no
        sleep-based waiting."""
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        with session_factory() as session:
            verdict = probe_post_state(
                session,
                CHAIN,
                header,
                txs,
                deadline=time.monotonic() - 0.001,
                proposer_signature=sig,
            )
        assert verdict == "post_state_timeout"

    def test_default_deadline_is_finite(self, session_factory, monkeypatch):
        """``deadline=None`` must derive a finite absolute budget from the
        configured positive timeout — never an unbounded backup."""
        seen = {}
        real = probe_mod._snapshot_source

        def spy(session, deadline):
            seen["deadline"] = deadline
            return real(session, deadline)

        monkeypatch.setattr(probe_mod, "_snapshot_source", spy)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        before = time.monotonic()
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None
        assert seen["deadline"] is not None
        # configured timeout is 10s — the derived deadline sits ~10s out.
        assert before + 1.0 < seen["deadline"] <= before + 11.0

    def test_contended_source_aborts_at_deadline_and_restores(self, session_factory):
        """busy_timeout lease regression: a second connection holding
        BEGIN EXCLUSIVE must not park a backup_step inside the production
        60s busy handler — the deadline aborts the copy, the refusal is
        ``post_state_timeout`` well under the 1s pragma, and the source
        connection's busy_timeout is restored to its exact original value
        with ``total_changes`` untouched."""
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        writer = sqlite3.connect(str(session_factory.db_path), timeout=0)
        writer.execute("BEGIN EXCLUSIVE")
        try:
            with session_factory() as session:
                raw = session.connection().connection.dbapi_connection
                raw.execute("PRAGMA busy_timeout=1000")
                before_changes = raw.total_changes
                start = time.monotonic()
                verdict = probe_post_state(
                    session,
                    CHAIN,
                    header,
                    txs,
                    deadline=start + 0.05,
                    proposer_signature=sig,
                )
                elapsed = time.monotonic() - start
                assert verdict == "post_state_timeout"
                assert elapsed < 0.4
                assert int(raw.execute("PRAGMA busy_timeout").fetchone()[0]) == 1000
                assert raw.total_changes == before_changes
        finally:
            writer.execute("ROLLBACK")
            writer.close()

    def test_busy_timeout_restored_on_success(self, session_factory):
        """The lease restores the exact original value on the success path
        too — the only source-connection change is nondurable."""
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        with session_factory() as session:
            raw = session.connection().connection.dbapi_connection
            raw.execute("PRAGMA busy_timeout=4321")
            try:
                verdict = probe_post_state(session, CHAIN, header, txs, deadline=time.monotonic() + 10, proposer_signature=sig)
                assert verdict is None
                assert int(raw.execute("PRAGMA busy_timeout").fetchone()[0]) == 4321
            finally:
                raw.execute("PRAGMA busy_timeout=0")

    def test_foreign_keys_pragmas_mirrored(self, session_factory):
        """The scratch destination mirrors the source connection's
        ``PRAGMA foreign_keys`` — an FK-ON source produces an FK-ON scratch
        where a real FK violation is rejected, while the identical write
        succeeds on an FK-OFF scratch. Every NOT NULL column is supplied, so
        the ON-case failure can only be the foreign key — not a shape error."""
        insert_sql = (
            "INSERT INTO escrow (job_id, chain_id, buyer, provider, amount, status, created_at,"
            " protected, current_milestone) VALUES (?,?,?,?,?,?,?,?,?)"
        )
        # buyer/provider have no account rows — only the FK can reject this.
        params = ("j-fk", CHAIN, "0x" + "99" * 20, "0x" + "88" * 20, 1, "locked", "2026-01-01 00:00:00+00:00", 0, 0)
        with session_factory() as session:
            raw = session.connection().connection.dbapi_connection
            raw.execute("PRAGMA foreign_keys=ON")
            try:
                dest = probe_mod._snapshot_source(session, time.monotonic() + 10)
                assert not isinstance(dest, str)
                try:
                    assert dest.execute("PRAGMA foreign_keys").fetchone()[0] == 1
                    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
                        dest.execute(insert_sql, params)
                finally:
                    dest.close()
            finally:
                raw.execute("PRAGMA foreign_keys=OFF")
        with session_factory() as session:
            raw = session.connection().connection.dbapi_connection
            raw.execute("PRAGMA foreign_keys=OFF")
            dest = probe_mod._snapshot_source(session, time.monotonic() + 10)
            try:
                assert dest.execute("PRAGMA foreign_keys").fetchone()[0] == 0
                # Same violating write succeeds with FK enforcement off —
                # proves the ON-case rejection was the constraint itself.
                dest.execute(insert_sql, params)
            finally:
                dest.close()

    @pytest.mark.asyncio
    async def test_worker_exception_maps_to_error(self, session_factory, monkeypatch):
        """A non-cancellation worker exception refuses ``post_state_error``
        and logs only the exception type — it never escapes the handler."""
        svc = _svc(session_factory)

        def boom(*a, **k):
            raise RuntimeError("worker blew up")

        monkeypatch.setattr(svc, "_v9_check_transactions", boom)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        assert await svc._run_post_state_probe(header, txs, sig) == "post_state_error"

    def test_int_header_height_overflow(self):
        assert _int_header_height({"height": 10}) == 10
        assert _int_header_height({"height": float("inf")}) == -1
        assert _int_header_height({"height": float("nan")}) == -1


# --------------------------------------------------------------------------
# pooled source discard when busy_timeout restore fails (#1984 F4)
# --------------------------------------------------------------------------

_PROBE_BUSY_MS = 4000


class _RestoreFailConnection(sqlite3.Connection):
    """sqlite3.Connection that injects restore failure only after the lease."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._leased = False

    def execute(self, sql, parameters=()):  # type: ignore[override]
        sql_s = str(sql)
        if "busy_timeout=0" in sql_s:
            self._leased = True
            return super().execute(sql, parameters)
        if self._leased and "busy_timeout=" in sql_s and "=0" not in sql_s:
            raise sqlite3.OperationalError("injected busy_timeout restore failure")
        return super().execute(sql, parameters)


def _pooled_probe_engine(tmp_path: Path, *, restore_fail: bool = False):
    """QueuePool scratch engine with a fixed 4000ms busy_timeout on checkouts."""
    from sqlalchemy.pool import QueuePool

    db_path = tmp_path / "probe-pool.db"
    sqlite3.connect(db_path).close()
    sentinel = {"restore_fail": restore_fail}

    def _creator():
        if sentinel["restore_fail"]:
            raw = sqlite3.connect(
                db_path,
                timeout=_PROBE_BUSY_MS / 1000.0,
                check_same_thread=False,
                factory=_RestoreFailConnection,
            )
        else:
            raw = sqlite3.connect(db_path, timeout=_PROBE_BUSY_MS / 1000.0, check_same_thread=False)
        raw.execute(f"PRAGMA busy_timeout={_PROBE_BUSY_MS}")
        return raw

    engine = create_engine(
        "sqlite://",
        poolclass=QueuePool,
        creator=_creator,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=False,
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sentinel (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO sentinel (id, value) VALUES (1, 'keep-me')"))
    return engine, db_path


def _sentinel_value(db_path: Path) -> str:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT value FROM sentinel WHERE id=1").fetchone()
        assert row is not None
        return str(row[0])
    finally:
        conn.close()


class TestConnectionDiscardOnRestoreFailure:
    def test_healthy_pool_checkout_restores_busy_and_reuses_raw(self, tmp_path):
        engine, db_path = _pooled_probe_engine(tmp_path)
        try:
            with Session(engine) as session:
                raw = session.connection().connection.dbapi_connection
                raw_id = id(raw)
                before = _sentinel_value(db_path)
                dest = probe_mod._snapshot_source(session, time.monotonic() + 10)
                assert not isinstance(dest, str)
                dest.close()
                raw_after = session.connection().connection.dbapi_connection
                assert id(raw_after) == raw_id
                assert int(raw_after.execute("PRAGMA busy_timeout").fetchone()[0]) == _PROBE_BUSY_MS
                assert _sentinel_value(db_path) == before == "keep-me"
        finally:
            engine.dispose()

    def test_restore_failure_discards_raw_and_next_checkout_is_fresh(self, tmp_path):
        engine, db_path = _pooled_probe_engine(tmp_path, restore_fail=True)
        try:
            with Session(engine) as session:
                conn = session.connection()
                raw = conn.connection.dbapi_connection
                raw_id = id(raw)
                before = _sentinel_value(db_path)
                verdict = probe_mod._snapshot_source(session, time.monotonic() + 10)
                assert verdict == "post_state_snapshot_failed"
                assert _sentinel_value(db_path) == before == "keep-me"
                with pytest.raises(sqlite3.ProgrammingError):
                    raw.execute("SELECT 1")
                session.close()
                with Session(engine) as session2:
                    raw2 = session2.connection().connection.dbapi_connection
                    assert id(raw2) != raw_id
                    assert int(raw2.execute("PRAGMA busy_timeout").fetchone()[0]) == _PROBE_BUSY_MS
        finally:
            engine.dispose()

    def test_backup_timeout_plus_restore_failure_still_discards(self, tmp_path):
        engine, db_path = _pooled_probe_engine(tmp_path, restore_fail=True)
        before = _sentinel_value(db_path)
        writer = sqlite3.connect(db_path, timeout=0)
        writer.execute("BEGIN EXCLUSIVE")
        try:
            with Session(engine) as session:
                conn = session.connection()
                raw = conn.connection.dbapi_connection
                raw_id = id(raw)
                verdict = probe_mod._snapshot_source(session, time.monotonic() + 0.05)
                assert verdict == "post_state_timeout"
                with pytest.raises(sqlite3.ProgrammingError):
                    raw.execute("SELECT 1")
                session.close()
                with Session(engine) as session2:
                    raw2 = session2.connection().connection.dbapi_connection
                    assert id(raw2) != raw_id
                    assert int(raw2.execute("PRAGMA busy_timeout").fetchone()[0]) == _PROBE_BUSY_MS
        finally:
            writer.execute("ROLLBACK")
            writer.close()
            engine.dispose()
        assert _sentinel_value(db_path) == before == "keep-me"

    def test_invalidate_failure_uses_detach_close_fallback(self, tmp_path, monkeypatch):
        engine, db_path = _pooled_probe_engine(tmp_path, restore_fail=True)
        try:
            with Session(engine) as session:
                conn = session.connection()
                raw = conn.connection.dbapi_connection
                raw_id = id(raw)

                def _boom_invalidate() -> None:
                    raise RuntimeError("invalidate blew up")

                monkeypatch.setattr(conn, "invalidate", _boom_invalidate)
                before = _sentinel_value(db_path)
                verdict = probe_mod._snapshot_source(session, time.monotonic() + 10)
                assert verdict == "post_state_snapshot_failed"
                assert _sentinel_value(db_path) == before == "keep-me"
                with pytest.raises(sqlite3.ProgrammingError):
                    raw.execute("SELECT 1")
                session.close()
                with Session(engine) as session2:
                    raw2 = session2.connection().connection.dbapi_connection
                    assert id(raw2) != raw_id
                    assert int(raw2.execute("PRAGMA busy_timeout").fetchone()[0]) == _PROBE_BUSY_MS
        finally:
            engine.dispose()


# --------------------------------------------------------------------------
# process-state isolation — source rows, singleton caches, side-effect
# channels, and a real side-table transaction
# --------------------------------------------------------------------------


class TestProcessIsolation:
    def test_source_rows_and_singleton_caches_untouched(self, session_factory):
        from aitbc_chain.state.state_transition import get_state_transition

        st = get_state_transition()
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        nonces_before = dict(st._processed_nonces)
        hashes_before = set(st._processed_tx_hashes)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None
        assert st._processed_nonces == nonces_before
        assert st._processed_tx_hashes == hashes_before

    def test_no_process_side_effect_channels(self, session_factory, monkeypatch):
        """Cache writes, shadow-root hooks and mempool eviction must be
        unreachable under ``_probe`` — fail-if-called sentinels on a real
        apply, not just accessor-property checks."""

        def boom(*a, **k):
            raise AssertionError("process side-effect channel touched during probe")

        class _ExplodingCache:
            def __getattr__(self, name):
                raise AssertionError(f"cache attribute {name} touched")

            def __setitem__(self, k, v):
                raise AssertionError("cache write during probe")

            def __delitem__(self, k):
                raise AssertionError("cache delete during probe")

        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        # Patch only after the request's clone-apply — that legitimately
        # uses the default (cache-enabled) transition.
        monkeypatch.setattr(state_transition_apply, "_cache", _ExplodingCache())
        monkeypatch.setattr(side_root_shadow, "on_block_sealed", boom)
        monkeypatch.setattr(mempool_module, "get_mempool", boom)
        from aitbc_chain.sync_block_import import BlockImportMixin

        monkeypatch.setattr(BlockImportMixin, "_evict_included_from_mempool", boom)
        monkeypatch.setattr(BlockImportMixin, "_evict_rejected_from_mempool", boom)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None


class TestSideTableApply:
    def test_gpu_register_side_table_reproduces_and_refuses(self, session_factory, monkeypatch):
        """A real side-effect transaction — GPU_REGISTER writes the
        ``gpu_registration`` side table, a member of the v18 committed set —
        must reproduce the claimed roots on the scratch apply: accept
        honest, refuse forged account *and* aux roots. The payload carries
        every field validation requires (``miner_id`` included), so the tx
        genuinely applies — a failed tx with matching no-op roots would
        prove nothing."""
        # v18: gpu_registration is committed and the era is aux-verifiable,
        # so the side-table write is bound by both claimed roots.
        monkeypatch.setattr(settings, "state_transition_v18_height", HEIGHT)
        tx = _attach_sender_sig(
            {
                "from": SENDER,
                "to": SENDER,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "GPU_REGISTER",
                "chain_id": CHAIN,
                "payload": {
                    "gpu_id": "gpu-probe-1",
                    "miner_id": "miner-probe-1",
                    "model": "test-gpu",
                    "memory_gb": 16,
                    "price_per_hour": "1.5",
                    "cuda_version": "12.0",
                    "region": "test",
                    "capabilities": [],
                },
            },
            SENDER_KEY,
        )
        txs = [_with_tx_hash(tx)]
        header, txs, sig = _request(session_factory, txs)

        # Spy on the *scratch* apply inside the probe: the GPU row must
        # actually exist in the snapshot session with the expected fields —
        # primitives only, since the scratch session dies with the probe.
        real_append = _AttestationProbeImporter._append_block
        seen: dict[str, tuple] = {}

        def _spy_append(self, session, block_data, transactions, **kwargs):
            result = real_append(self, session, block_data, transactions, **kwargs)
            if getattr(result, "accepted", False):
                row = session.exec(
                    select(GPURegistration).where(
                        GPURegistration.chain_id == CHAIN,
                        GPURegistration.gpu_id == "gpu-probe-1",
                    )
                ).first()
                if row is not None:
                    seen["gpu"] = (
                        row.model,
                        row.memory_gb,
                        row.status,
                        canonical_address(row.registered_by),
                    )
            return result

        monkeypatch.setattr(_AttestationProbeImporter, "_append_block", _spy_append)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None

        assert seen.get("gpu") == ("test-gpu", 16, "active", canonical_address(SENDER))
        # The speculative write never reached the source database.
        with session_factory() as session:
            assert (
                session.exec(
                    select(GPURegistration).where(
                        GPURegistration.chain_id == CHAIN,
                        GPURegistration.gpu_id == "gpu-probe-1",
                    )
                ).first()
                is None
            )

        # Refusal 1: claim the post-state of a *different* transaction set —
        # the side-table write makes the account-root divergence real.
        other = _with_tx_hash(_tx(value=6000))
        other_header, _, _ = _request(session_factory, [other])
        forged = dict(header, state_root=other_header["state_root"])
        assert _probe(session_factory, forged, txs, proposer_signature=sig) == "post_state_apply_refused"

        # Refusal 2: forge the *aux* root — at v18 gpu_registration is in
        # the committed set, so a wrong aux digest must reject even with an
        # honest account root. The header is rehashed so the claim is
        # well-formed.
        forged_aux = dict(header, aux_state_root=other_header["aux_state_root"])
        forged_aux["hash"] = compute_block_hash(
            CHAIN,
            HEIGHT,
            PARENT_HASH,
            TS,
            forged_aux["tx_hashes"],
            PROPOSER,
            str(forged_aux["state_root"] or ""),
            str(forged_aux["bridge_state_root"] or ""),
            str(forged_aux["aux_state_root"] or ""),
        )
        assert _probe(session_factory, forged_aux, txs, proposer_signature=sig) == "post_state_apply_refused"


# --------------------------------------------------------------------------
# listener gate — an armed post-state probe refuses regardless of the
# legacy v9 activation height, before any durable lock or signature
# --------------------------------------------------------------------------


class _StubBroker:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, message: dict):
        self.published.append((topic, message))


def _boom(*a, **k):
    raise AssertionError("must not be called for a refused attestation")


class TestListenerProbeGate:
    def _listener_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        monkeypatch.setattr(settings, "consensus_enforce_proposer_schedule", False)
        monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
        monkeypatch.setattr(settings, "vote_journal_abandon_enabled", False)
        monkeypatch.setattr(settings, "chain_id", CHAIN)
        broker = _StubBroker()
        monkeypatch.setattr(ra_module, "gossip_broker", broker)
        return broker

    def _service(self, session_factory, tmp_path):
        our_key = "0x" + "66" * 32
        svc = RemoteAttestationService(CHAIN, {derive_ethereum_address(our_key): our_key}, session_factory=session_factory)
        svc._round_locks_path = tmp_path / "locks.json"
        return svc

    def _fresh_request(self, session_factory):
        """A hash-valid request with a *fresh* header timestamp — the
        listener's staleness bound requires it. No proposer_signature: the
        probe's armed signature policy supplies the refusal."""
        txs = [_with_tx_hash(_tx())]
        header, txs, _sig = _request(session_factory, txs)
        header["timestamp"] = datetime.now(UTC).isoformat()
        header["hash"] = compute_block_hash(
            CHAIN,
            HEIGHT,
            PARENT_HASH,
            header["timestamp"],
            header["tx_hashes"],
            PROPOSER,
            str(header["state_root"] or ""),
            str(header["bridge_state_root"] or ""),
            str(header["aux_state_root"] or ""),
        )
        return {"header": header, "transactions": txs}

    @pytest.mark.asyncio
    async def test_pre_v9_active_probe_refuses_before_lock_and_sign(self, session_factory, monkeypatch, tmp_path):
        """#1940 F4/D: with the post-state gate armed at a height whose block
        version is still <9, the probe refusal is ENFORCED — the old v9
        height gate would only have shadow-logged. The refusal lands before
        ``_record_pre_sign_lock`` and before any attestation signature."""
        broker = self._listener_settings(monkeypatch)
        svc = self._service(session_factory, tmp_path)
        monkeypatch.setattr(svc, "_record_pre_sign_lock", _boom)
        import aitbc_chain.consensus.remote_attestation_listener as listener_mod

        monkeypatch.setattr(listener_mod, "_sign_attestation", _boom)
        request = self._fresh_request(session_factory)
        assert get_block_version_for_height(HEIGHT) < 9  # genuinely pre-v9
        await svc._handle_request(request)
        assert broker.published == []

    @pytest.mark.asyncio
    async def test_v9_active_probe_refuses_before_lock_and_sign(self, session_factory, monkeypatch, tmp_path):
        """Same no-lock/no-sign property on the ordinary v9+ path: an armed
        F4 probe refusal is enforced identically."""
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)
        broker = self._listener_settings(monkeypatch)
        svc = self._service(session_factory, tmp_path)
        monkeypatch.setattr(svc, "_record_pre_sign_lock", _boom)
        import aitbc_chain.consensus.remote_attestation_listener as listener_mod

        monkeypatch.setattr(listener_mod, "_sign_attestation", _boom)
        request = self._fresh_request(session_factory)
        assert get_block_version_for_height(HEIGHT) >= 9
        await svc._handle_request(request)
        assert broker.published == []


# --------------------------------------------------------------------------
# #2003 ATTEST-POSTSTATE-PROBE-ARMING-1 — Python-side deadline arming (F1)
# and the DB-size pre-flight (F2)
# --------------------------------------------------------------------------


class TestProbeDeadlineArming:
    def test_expired_deadline_during_apply_maps_to_timeout(self, session_factory, monkeypatch):
        """F1: the sqlite progress handler cannot preempt pure-Python apply
        work, so ``_append_block`` re-checks the deadline at coarse loop
        boundaries. Expiring the budget the moment the apply starts must
        surface as ``post_state_timeout`` — never ``post_state_error`` and
        never a runaway holding the single-flight probe lock."""
        import aitbc_chain.sync_block_import as sbi

        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        real_mono = time.monotonic
        expired = [False]

        def fake_mono() -> float:
            return real_mono() + (1000.0 if expired[0] else 0.0)

        fake_time = SimpleNamespace(monotonic=fake_mono, perf_counter=time.perf_counter)
        # Patch only the two modules' ``time`` bindings — the global time
        # module (and pytest's own clocks) stay real.
        monkeypatch.setattr(sbi, "time", fake_time)
        monkeypatch.setattr(probe_mod, "time", fake_time)

        real_apply = probe_mod._apply_and_verify

        def _expiring_apply(*a, **kw):
            expired[0] = True
            return real_apply(*a, **kw)

        monkeypatch.setattr(probe_mod, "_apply_and_verify", _expiring_apply)
        with session_factory() as session:
            verdict = probe_post_state(
                session,
                CHAIN,
                header,
                txs,
                deadline=real_mono() + 30,
                proposer_signature=sig,
            )
        assert verdict == "post_state_timeout"

    def test_state_root_compute_expired_deadline_raises(self):
        """``StateManager.compute_state_root`` honours its deadline param —
        an already-expired budget raises ``TimeoutError`` on the first
        checkpoint instead of grinding through the trie."""
        from aitbc_chain.state.merkle_patricia_trie import StateManager

        accounts = {"0x" + "ab" * 20: Account(chain_id=CHAIN, address="0x" + "ab" * 20, balance=1, nonce=0)}
        with pytest.raises(TimeoutError):
            StateManager().compute_state_root(accounts, deadline=time.monotonic() - 1)

    def test_state_root_compute_deadline_mid_iteration(self, monkeypatch):
        """The check fires every 8192 sorted accounts: a clock that expires
        only after the first checkpoint must raise mid-iteration, proving
        the loop — not just the entry — is bounded."""
        import aitbc_chain.state.merkle_patricia_trie as mpt

        accounts = {}
        for i in range(8300):
            addr = "0x" + f"{i:040x}"
            accounts[addr] = Account(chain_id=CHAIN, address=addr, balance=i, nonce=i)
        ticks = iter([0.0] + [10_000.0] * 64)
        fake_time = SimpleNamespace(monotonic=lambda: next(ticks))
        monkeypatch.setattr(mpt, "time", fake_time)
        from aitbc_chain.state.merkle_patricia_trie import StateManager

        with pytest.raises(TimeoutError):
            StateManager().compute_state_root(accounts, deadline=100.0)

    def test_state_root_full_deadline_none_unchanged(self, session_factory):
        """Non-regression: ``deadline=None`` keeps the legacy signature and
        result — the probe's own clone-apply already relies on this."""
        with session_factory() as session:
            root = compute_state_root_full(session, CHAIN)
            assert root is not None and root.startswith("0x")
            root_dl = compute_state_root_full(session, CHAIN, deadline=time.monotonic() + 30)
            assert root_dl == root

    def test_committed_fingerprint_deadline_raises(self, session_factory):
        with session_factory() as session:
            conn = session.connection().connection
            with pytest.raises(TimeoutError):
                side_root_shadow.committed_fingerprint(conn, None, deadline=time.monotonic() - 1)
            # deadline=None path unchanged.
            fp = side_root_shadow.committed_fingerprint(conn)
            assert "fingerprint" in fp

    def test_execute_groups_deadline_raises(self):
        from aitbc.parallel.executor import ParallelExecutor

        executor = ParallelExecutor(max_workers=1)
        try:
            with pytest.raises(TimeoutError):
                executor.execute_groups([["a"], ["b"]], lambda x: x, deadline=time.monotonic() - 1)
            # deadline=None path unchanged.
            assert executor.execute_groups([[1, 2], [3]], lambda x: x * 2) == [[2, 4], [6]]
        finally:
            executor.close()


class TestProbeDbSizePreflight:
    def test_oversized_db_refused(self, session_factory, monkeypatch):
        """F2: a source DB larger than ``attestation_post_state_max_db_bytes``
        refuses ``post_state_db_too_large`` before the :memory: backup —
        the copy alone cannot fit the probe budget on multi-GB files."""
        monkeypatch.setattr(settings, "attestation_post_state_max_db_bytes", 1)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        assert _probe(session_factory, header, txs, proposer_signature=sig) == "post_state_db_too_large"

    def test_zero_bound_disables_size_guard(self, session_factory, monkeypatch):
        monkeypatch.setattr(settings, "attestation_post_state_max_db_bytes", 0)
        txs = [_with_tx_hash(_tx())]
        header, txs, sig = _request(session_factory, txs)
        assert _probe(session_factory, header, txs, proposer_signature=sig) is None

    def test_memory_bind_skips_size_check(self, session_factory, monkeypatch):
        """A non-file bind (:memory:) has no path to stat — the guard must
        skip it rather than refuse or crash."""
        monkeypatch.setattr(settings, "attestation_post_state_max_db_bytes", 1)
        engine = create_engine("sqlite://")
        chain_metadata.create_all(engine)
        with Session(engine) as session:
            assert probe_mod._source_db_file_bytes(session) is None
            dest = probe_mod._snapshot_source(session, time.monotonic() + 10)
            assert not isinstance(dest, str) or dest != "post_state_db_too_large"
            if not isinstance(dest, str):
                dest.close()
