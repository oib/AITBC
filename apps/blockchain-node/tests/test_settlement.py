"""B12: Integration tests for CrossChainSettlementService (v0.9.0).

Tests the HTLC-based atomic settlement lifecycle and proof chain using an
in-memory mock DB (no real database required). The settlement service calls
the Python-native HTLCContract (B4) to move funds between accounts — the
state transitions, fund movement, and proof chain are real and verifiable.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from types import SimpleNamespace

# Ensure blockchain-node source is importable
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aitbc.settlement.htlc import (  # noqa: E402
    HTLCStateMachine,
    HTLCState,
    calculate_dest_timelock,
    calculate_source_timelock,
    compute_hashlock,
    generate_secret,
    validate_timelocks,
    verify_secret,
)
from aitbc_chain.base_models import Account, CrossChainEscrowRecord, EscrowProofRecord, HTLCSwapState  # noqa: E402
from aitbc_chain.config import settings  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory mock DB
# ---------------------------------------------------------------------------


class _MockResult:
    """Mock query result supporting .scalars().first() and .scalars().all()."""

    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class MockSession:
    """In-memory mock SQLAlchemy session for settlement tests.

    Stores ``CrossChainEscrowRecord``, ``EscrowProofRecord``, ``Account``, and
    ``HTLCSwapState`` instances in dicts keyed by primary key. Supports the
    subset of the Session API used by ``CrossChainSettlementService`` and
    ``HTLCContract``: ``execute``, ``add``, ``commit``, ``refresh``, ``get``,
    ``flush``.
    """

    def __init__(self):
        self.escrows: dict[str, CrossChainEscrowRecord] = {}
        self.proofs: list[EscrowProofRecord] = []
        self.accounts: dict[tuple[str, str], Account] = {}
        self.swaps: dict[str, HTLCSwapState] = {}
        # Chain heads by chain_id. Escrow creation reads the real head of both
        # chains to compute HTLC timelocks -- it used to invent one from
        # time.time(), so these tests never had to model a chain that had
        # produced blocks. Seeded with a plausible height for both islands.
        self.block_heights: dict[str, int] = {"ait-hub": 10_000, "ait-island-1": 8_000}
        self._escrow_counter = 0
        self._proof_counter = 0

    # -- write side --------------------------------------------------------

    def add(self, record):
        if isinstance(record, CrossChainEscrowRecord):
            if record.id is None:
                self._escrow_counter += 1
                record.id = self._escrow_counter
            self.escrows[record.escrow_id] = record
        elif isinstance(record, EscrowProofRecord):
            if record.id is None:
                self._proof_counter += 1
                record.id = self._proof_counter
            # Replace existing proof with same id (re-add pattern)
            self.proofs = [p for p in self.proofs if p.id != record.id]
            self.proofs.append(record)
        elif isinstance(record, Account):
            self.accounts[(record.chain_id, record.address)] = record
        elif isinstance(record, HTLCSwapState):
            self.swaps[record.swap_id] = record

    def get(self, model_cls, primary_key):
        if model_cls is Account:
            return self.accounts.get(primary_key)
        elif model_cls is HTLCSwapState:
            return self.swaps.get(primary_key)
        elif model_cls is CrossChainEscrowRecord:
            return self.escrows.get(primary_key)
        return None

    def flush(self):
        pass

    def commit(self):
        pass

    def refresh(self, record):
        pass  # records are stored by reference; no refresh needed

    # -- read side ---------------------------------------------------------

    def execute(self, stmt):
        froms = stmt.get_final_froms()
        table_name = froms[0].name if froms else ""
        where = stmt.whereclause
        filters = self._extract_filters(where)

        if table_name == "cross_chain_escrows":
            rows = list(self.escrows.values())
            if "escrow_id" in filters:
                rows = [r for r in rows if r.escrow_id == filters["escrow_id"]]
            if "status" in filters:
                rows = [r for r in rows if r.status in filters["status"]]
            # #2266 dedupe lookup filters on the full request tuple
            for key in ("trade_id", "source_chain", "dest_chain", "sender", "recipient", "amount"):
                if key in filters:
                    rows = [r for r in rows if getattr(r, key) == filters[key]]
        elif table_name == "block":
            chain_id = filters.get("chain_id")
            height = self.block_heights.get(chain_id) if chain_id else None
            rows = (
                [SimpleNamespace(height=height, hash=f"0x{chain_id}head".ljust(66, "0"), chain_id=chain_id)]
                if height is not None
                else []
            )
        elif table_name == "escrow_proofs":
            rows = list(self.proofs)
            if "escrow_id" in filters:
                rows = [r for r in rows if r.escrow_id == filters["escrow_id"]]
            # Handle order_by id desc (used by _get_last_proof_hash)
            if stmt._order_by_clauses:
                rows.sort(key=lambda r: r.id, reverse=True)
        else:
            rows = []

        return _MockResult(rows)

    def _extract_filters(self, where) -> dict:
        """Extract column→value filters from a SQLAlchemy where clause."""
        filters: dict = {}
        if where is None:
            return filters

        # Flatten AND'd conditions
        clauses = [where]
        if hasattr(where, "clauses") and where.operator.__name__ == "and_":
            clauses = list(where.clauses)

        for clause in clauses:
            col = clause.left
            key = getattr(col, "key", str(col))
            op = clause.operator
            right = clause.right

            if op.__name__ == "eq":
                val = getattr(right, "value", right)
                filters[key] = val
            elif op.__name__ == "in_op":
                val = getattr(right, "value", right)
                filters[key] = val
        return filters


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a fresh MockSession and patch session_scope to use it."""
    session = MockSession()

    # Pre-fund common test accounts for HTLC contract operations (B4)
    for addr, balance in [("alice", 100000), ("bob", 50000)]:
        session.add(Account(chain_id="ait-hub", address=addr, balance=balance, nonce=0))
    session.flush()

    @contextmanager
    def fake_scope(chain_id: str = ""):
        yield session

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("aitbc_chain.cross_chain.settlement.session_scope", fake_scope)
        yield session


@pytest.fixture(autouse=True)
def enable_escrow():
    """Enable escrow for all settlement tests, restore afterwards."""
    original = settings.escrow_enabled
    settings.escrow_enabled = True
    yield
    settings.escrow_enabled = original


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSettlementService:
    """B12: CrossChainSettlementService tests."""

    # -- create_escrow -----------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_escrow_refuses_retired_before_any_state(self, mock_session):
        """#2385: the HTLC rail is retired — create_escrow fails fast with
        RetiredProtocolTransfer before minting a never-lockable record,
        so the #2265/#2266 provisioning/dedupe paths are unreachable."""
        from aitbc_chain.cross_chain.settlement import CrossChainSettlementService
        from aitbc_chain.rpc.retired import RetiredProtocolTransfer

        svc = CrossChainSettlementService(chain_id="ait-hub")
        with pytest.raises(RetiredProtocolTransfer, match="inter-chain HTLC settlement is retired"):
            await svc.create_escrow(
                trade_id="trade_x",
                source_chain="ait-hub",
                dest_chain="ait-unprovisioned",
                sender="alice",
                recipient="bob",
                amount=100,
            )
        assert mock_session.escrows == {}

    # -- lock_escrow -------------------------------------------------------

    # -- verify_lock -------------------------------------------------------

    # -- happy path --------------------------------------------------------

    # -- refund ------------------------------------------------------------

    # -- proof chain -------------------------------------------------------

    # -- extend_timeout ----------------------------------------------------

    # -- HTLC utility tests (no DB mocking needed) -------------------------

    def test_htlc_secret_verification(self):
        """Secret matches hashlock."""
        secret = generate_secret()
        hashlock = compute_hashlock(secret)

        # Correct secret verifies
        assert verify_secret(secret, hashlock)

        # Wrong secret does not verify
        wrong = generate_secret()
        assert not verify_secret(wrong, hashlock)

        # Empty secret does not verify
        assert not verify_secret("", hashlock)

    def test_htlc_secret_length(self):
        """Generated secret is 32 bytes (64 hex chars)."""
        secret = generate_secret()
        assert len(secret) == 64
        # Should be valid hex
        int(secret, 16)

    def test_htlc_secret_uniqueness(self):
        """Each generated secret is unique."""
        secrets = {generate_secret() for _ in range(100)}
        assert len(secrets) == 100

    def test_escrow_to_dict_never_leaks_preimage(self):
        """_escrow_to_dict must not expose the HTLC preimage by default.

        GET /settlement/{escrow_id} is unauthenticated; returning ``secret``
        there leaks the preimage before settlement and lets any reader
        front-run the destination-leg claim. Only the create response to the
        initiator (``include_secret=True``) may carry it.
        """
        from aitbc_chain.cross_chain.settlement import _escrow_to_dict

        record = CrossChainEscrowRecord(
            escrow_id="esc_test",
            trade_id="trade_test",
            source_chain="a",
            dest_chain="b",
            sender="0xsender",
            recipient="0xrecipient",
            amount=1,
            asset="AITBC",
            status="locked",
            secret_hash="0" * 64,
            secret=generate_secret(),
        )
        public = _escrow_to_dict(record)
        assert "secret" not in public
        assert public["secret_hash"] == "0" * 64
        assert _escrow_to_dict(record, include_secret=True)["secret"] == record.secret

    def test_timelock_validation(self):
        """Invalid timelocks rejected."""
        # Valid timelocks: dest expires before source with sufficient margin
        source_tl = 1000
        dest_tl = 500
        errors = validate_timelocks(
            source_timelock=source_tl,
            dest_timelock=dest_tl,
            source_current_height=100,
            dest_current_height=100,
            source_block_time=5,
            dest_block_time=5,
            min_margin_seconds=300,
        )
        assert errors == [], f"Expected valid, got: {errors}"

    def test_timelock_validation_source_in_past(self):
        """Source timelock in the past is rejected."""
        errors = validate_timelocks(
            source_timelock=50,
            dest_timelock=500,
            source_current_height=100,
            dest_current_height=100,
        )
        assert any("Source timelock" in e for e in errors)

    def test_timelock_validation_dest_in_past(self):
        """Dest timelock in the past is rejected."""
        errors = validate_timelocks(
            source_timelock=1000,
            dest_timelock=50,
            source_current_height=100,
            dest_current_height=100,
        )
        assert any("Dest timelock" in e for e in errors)

    def test_timelock_validation_dest_after_source(self):
        """Dest timelock expiring after source is rejected."""
        # dest has more remaining blocks with same block time → expires later
        errors = validate_timelocks(
            source_timelock=200,
            dest_timelock=300,
            source_current_height=100,
            dest_current_height=100,
            source_block_time=5,
            dest_block_time=5,
        )
        assert any("must expire before source" in e for e in errors)

    def test_timelock_validation_insufficient_margin(self):
        """Insufficient margin between dest and source is rejected."""
        # dest expires 1 block (5s) before source — margin < 300s
        errors = validate_timelocks(
            source_timelock=110,
            dest_timelock=109,
            source_current_height=100,
            dest_current_height=100,
            source_block_time=5,
            dest_block_time=5,
            min_margin_seconds=300,
        )
        assert any("Margin" in e for e in errors)

    def test_calculate_source_timelock(self):
        """Source timelock calculation."""
        tl = calculate_source_timelock(
            current_block_height=100,
            timeout_seconds=3600,
            block_time_seconds=5,
            margin_blocks=10,
        )
        # 3600 // 5 = 720 blocks + 10 margin + 100 current = 830
        assert tl == 830

    def test_calculate_dest_timelock(self):
        """Dest timelock expires before source, measured from each chain's own head.

        The previous version of this test multiplied both absolute heights by
        their block times and compared the products -- treating a height as a
        duration, the same error the function under test was making. Both sides
        shared the mistake, so it passed while the calculation was wrong.

        The property that matters is about *remaining* time from each chain's
        current height, which is what validate_timelocks checks.
        """
        source_head, dest_head = 100, 5_000
        source_tl = calculate_source_timelock(source_head, 3600, 5)
        dest_tl = calculate_dest_timelock(
            source_timelock=source_tl,
            source_current_height=source_head,
            source_block_time=5,
            dest_current_height=dest_head,
            dest_block_time=3,
        )

        source_remaining_s = (source_tl - source_head) * 5
        dest_remaining_s = (dest_tl - dest_head) * 3
        assert dest_remaining_s < source_remaining_s

    def test_dest_timelock_satisfies_the_validator(self):
        """The calculator's output must pass the validator in the same module.

        This is the assertion that fails against the old implementation, which
        produced a dest timelock the validator rejected outright.
        """
        source_head, dest_head = 1_000_000, 100
        source_tl = calculate_source_timelock(source_head, 3600, 5)
        dest_tl = calculate_dest_timelock(
            source_timelock=source_tl,
            source_current_height=source_head,
            source_block_time=5,
            dest_current_height=dest_head,
            dest_block_time=10,
        )

        assert (
            validate_timelocks(
                source_timelock=source_tl,
                dest_timelock=dest_tl,
                source_current_height=source_head,
                dest_current_height=dest_head,
                source_block_time=5,
                dest_block_time=10,
            )
            == []
        )

    def test_dest_timelock_tracks_the_dest_chain_head(self):
        """A different dest head must move the dest timelock with it.

        The old implementation ignored dest_current_height entirely, so the same
        source timelock produced the same dest height whether the dest chain was
        at block 100 or block 600,000 -- weeks away in one case, already expired
        in the other.
        """
        source_head = 1_000_000
        source_tl = calculate_source_timelock(source_head, 3600, 5)

        def dest_for(dest_head: int) -> int:
            return calculate_dest_timelock(
                source_timelock=source_tl,
                source_current_height=source_head,
                source_block_time=5,
                dest_current_height=dest_head,
                dest_block_time=10,
            )

        low, high = dest_for(100), dest_for(600_000)
        assert high - low == 600_000 - 100
        # And both are the same distance ahead of their own chain's head.
        assert low - 100 == high - 600_000

    def test_dest_timelock_margin_is_never_less_than_requested(self):
        """Flooring into whole dest blocks must only ever increase the margin."""
        source_head, dest_head, margin = 1_000, 42, 300
        for dest_block_time in (1, 3, 7, 11, 30):
            source_tl = calculate_source_timelock(source_head, 3600, 5)
            dest_tl = calculate_dest_timelock(
                source_timelock=source_tl,
                source_current_height=source_head,
                source_block_time=5,
                dest_current_height=dest_head,
                dest_block_time=dest_block_time,
                margin_seconds=margin,
            )
            source_remaining_s = (source_tl - source_head) * 5
            dest_remaining_s = (dest_tl - dest_head) * dest_block_time
            assert source_remaining_s - dest_remaining_s >= margin, f"dest_block_time={dest_block_time}"

    def test_dest_timelock_refuses_an_expired_source(self):
        with pytest.raises(ValueError, match="not above source_current_height"):
            calculate_dest_timelock(
                source_timelock=100,
                source_current_height=100,
                source_block_time=5,
                dest_current_height=0,
                dest_block_time=5,
            )

    def test_dest_timelock_refuses_a_window_too_short_for_the_margin(self):
        # 2 blocks x 5s = 10s of source window, against a 300s margin.
        with pytest.raises(ValueError, match="too short"):
            calculate_dest_timelock(
                source_timelock=102,
                source_current_height=100,
                source_block_time=5,
                dest_current_height=0,
                dest_block_time=5,
            )

    def test_htlc_state_machine_valid_transitions(self):
        """HTLC state machine allows valid transitions."""
        sm = HTLCStateMachine()
        assert sm.can_transition(HTLCState.CREATED, HTLCState.FUNDED)
        assert sm.can_transition(HTLCState.FUNDED, HTLCState.COMPLETED)
        assert sm.can_transition(HTLCState.FUNDED, HTLCState.REFUNDED)
        assert sm.can_transition(HTLCState.EXPIRED, HTLCState.REFUNDED)

    def test_htlc_state_machine_invalid_transitions(self):
        """HTLC state machine rejects invalid transitions."""
        sm = HTLCStateMachine()
        assert not sm.can_transition(HTLCState.CREATED, HTLCState.COMPLETED)
        assert not sm.can_transition(HTLCState.COMPLETED, HTLCState.FUNDED)
        assert not sm.can_transition(HTLCState.REFUNDED, HTLCState.COMPLETED)
        with pytest.raises(ValueError, match="Invalid HTLC state transition"):
            sm.transition(HTLCState.CREATED, HTLCState.COMPLETED)

    def test_htlc_state_machine_terminal(self):
        """Terminal states have no outgoing transitions."""
        sm = HTLCStateMachine()
        assert sm.is_terminal(HTLCState.COMPLETED)
        assert sm.is_terminal(HTLCState.REFUNDED)
        assert not sm.is_terminal(HTLCState.CREATED)
        assert not sm.is_terminal(HTLCState.FUNDED)

    # -- get_escrow / get_escrow_status ------------------------------------


# ---------------------------------------------------------------------------
# Refund terminality — a failed HTLC refund must not fabricate terminal state
# ---------------------------------------------------------------------------


class TestRefundTerminality:
    """A refused refund must never mark the escrow terminal.

    #2385 retired the HTLC rail outright: ``refund`` now fails fast with
    ``RetiredProtocolTransfer`` for every escrow — locked or never-locked —
    before touching state. ``check_timeouts`` catches that refusal and
    drives the expired non-terminal row to terminal ``failed`` (it can
    never settle or refund), so the 10s monitor does not retry-log it
    forever.
    """

    def _service(self):
        from aitbc_chain.cross_chain.settlement import CrossChainSettlementService

        return CrossChainSettlementService(chain_id="ait-hub")

    def _record(self, **overrides) -> CrossChainEscrowRecord:
        from datetime import UTC, datetime

        rec = CrossChainEscrowRecord(
            escrow_id="esc_refund",
            trade_id="trade_refund",
            source_chain="ait-hub",
            dest_chain="ait-island-1",
            sender="alice",
            recipient="bob",
            amount=100,
            asset="native",
            status="locked",
            secret_hash="ab" * 32,
            secret=generate_secret(),
            source_timelock=10_070,
            dest_timelock=8_000,
            timeout_seconds=3600,
            created_at=datetime.now(UTC),
            locked_at=datetime.now(UTC),
            source_lock_tx_hash="swap-1",
        )
        for key, value in overrides.items():
            setattr(rec, key, value)
        return rec

    @pytest.mark.asyncio
    async def test_refused_refund_stays_non_terminal(self, mock_session):
        """The retired HTLC mutator raises — the refusal propagates, no
        REFUNDED, no proof."""
        from aitbc_chain.rpc.retired import RetiredProtocolTransfer

        mock_session.add(self._record())
        mock_session.add(
            HTLCSwapState(
                swap_id="swap-1",
                initiator="alice",
                participant="bob",
                amount=100,
                hashlock="cd" * 32,
                timelock=10_070,  # mock head is 10_000 — 70 blocks early
                status="open",
            )
        )
        with pytest.raises(RetiredProtocolTransfer):
            await self._service().refund("esc_refund")
        assert mock_session.escrows["esc_refund"].status == "locked"
        assert mock_session.proofs == []

    @pytest.mark.asyncio
    async def test_refund_refuses_retired_for_never_locked_escrow(self, mock_session):
        """#2385: even a never-locked escrow cannot be refunded — the whole
        rail is retired, so refund fails fast and the record is untouched."""
        from aitbc_chain.rpc.retired import RetiredProtocolTransfer

        mock_session.add(self._record(source_lock_tx_hash=None, status="pending"))
        with pytest.raises(RetiredProtocolTransfer, match="inter-chain HTLC settlement is retired"):
            await self._service().refund("esc_refund")
        assert mock_session.escrows["esc_refund"].status == "pending"
        assert mock_session.proofs == []

    @pytest.mark.asyncio
    async def test_check_timeouts_retires_expired_row_to_failed(self, mock_session):
        """#2385: an expired non-terminal escrow can never refund — the
        monitor drives it to terminal ``failed`` once instead of
        retry-logging every 10s tick."""
        from datetime import UTC, datetime, timedelta

        old = datetime.now(UTC) - timedelta(seconds=3700)
        mock_session.add(self._record(created_at=old, locked_at=old))
        refunded = await self._service().check_timeouts()
        assert refunded == []
        assert mock_session.escrows["esc_refund"].status == "failed"

    @pytest.mark.asyncio
    async def test_check_timeouts_leaves_unexpired_row_alone(self, mock_session):
        """A non-terminal escrow still inside its timeout is not touched —
        the retired-rail sweep only fires on expiry."""
        mock_session.add(self._record(status="pending", source_lock_tx_hash=None))
        refunded = await self._service().check_timeouts()
        assert refunded == []
        assert mock_session.escrows["esc_refund"].status == "pending"


# ---------------------------------------------------------------------------
# #2385 — the whole HTLC settlement rail is retired
# ---------------------------------------------------------------------------


class TestSettlementRailRetired:
    """Every lifecycle mutator fails fast with RetiredProtocolTransfer before
    touching state; reads stay live so legacy escrow rows remain inspectable."""

    def _service(self):
        from aitbc_chain.cross_chain.settlement import CrossChainSettlementService

        return CrossChainSettlementService(chain_id="ait-hub")

    @pytest.mark.asyncio
    async def test_all_mutators_raise_retired(self, mock_session):
        from aitbc_chain.rpc.retired import RetiredProtocolTransfer

        svc = self._service()
        with pytest.raises(RetiredProtocolTransfer, match="inter-chain HTLC settlement is retired"):
            await svc.lock_escrow("esc_x")
        with pytest.raises(RetiredProtocolTransfer, match="inter-chain HTLC settlement is retired"):
            await svc.verify_lock("esc_x")
        with pytest.raises(RetiredProtocolTransfer, match="inter-chain HTLC settlement is retired"):
            await svc.execute_trade("esc_x")
        with pytest.raises(RetiredProtocolTransfer, match="inter-chain HTLC settlement is retired"):
            await svc.settle("esc_x", "deadbeef")
        with pytest.raises(RetiredProtocolTransfer, match="inter-chain HTLC settlement is retired"):
            await svc.refund("esc_x")
        with pytest.raises(RetiredProtocolTransfer, match="inter-chain HTLC settlement is retired"):
            await svc.extend_timeout("esc_x", 60)
        # Nothing was written — no escrow rows, no proofs.
        assert mock_session.escrows == {}
        assert mock_session.proofs == []

    @pytest.mark.asyncio
    async def test_reads_still_work(self, mock_session):
        from datetime import UTC, datetime

        mock_session.add(
            CrossChainEscrowRecord(
                escrow_id="esc_ro",
                trade_id="trade_ro",
                source_chain="ait-hub",
                dest_chain="ait-island-1",
                sender="alice",
                recipient="bob",
                amount=100,
                asset="native",
                status="pending",
                secret_hash="ab" * 32,
                secret=generate_secret(),
                created_at=datetime.now(UTC),
            )
        )
        svc = self._service()
        escrow = await svc.get_escrow("esc_ro")
        assert escrow is not None and escrow["escrow_id"] == "esc_ro"
        assert "secret" not in escrow  # preimage stays private on reads
        assert await svc.get_escrow_status("esc_ro") == "pending"
        assert await svc.get_proof_chain("esc_ro") == []


# ---------------------------------------------------------------------------
# Router auth — the settlement prefix moves funds and must not be public
# ---------------------------------------------------------------------------


class TestSettlementRouterAuth:
    """/rpc/bridge/settlement/* was reachable with no credentials while the
    sibling /rpc/escrow/ router required X-API-Key. The router now carries the
    same dependency; without the configured key every route must 403."""

    @pytest.fixture
    def client(self, monkeypatch):
        import aitbc_chain.rpc.escrow_routes as escrow_routes
        from aitbc_chain.rpc.routers.settlement import router as settlement_router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", "test-key-123")
        app = FastAPI()
        app.include_router(settlement_router, prefix="/rpc")
        return TestClient(app)

    def test_mutating_routes_reject_missing_key(self, client):
        for method, path in [
            ("post", "/rpc/bridge/settlement/esc_x/refund"),
            ("post", "/rpc/bridge/settlement/esc_x/dispute"),
            ("post", "/rpc/bridge/settlement/esc_x/resolve"),
            ("post", "/rpc/bridge/settlement/esc_x/lock"),
        ]:
            resp = getattr(client, method)(path, json={} if "dispute" in path or "resolve" in path else None)
            assert resp.status_code == 403, f"{method} {path} → {resp.status_code}"

    def test_mutating_routes_return_410_retired(self, client):
        """#2385: authenticated mutating calls hit the retired rail — every
        POST on this router answers 410 Gone, reads still reach the handler."""
        for method, path, body in [
            ("post", "/rpc/bridge/settlement/create", {"trade_id": "t"}),
            ("post", "/rpc/bridge/settlement/esc_x/lock", None),
            ("post", "/rpc/bridge/settlement/esc_x/verify", None),
            ("post", "/rpc/bridge/settlement/esc_x/execute", None),
            ("post", "/rpc/bridge/settlement/esc_x/settle", {"secret": "s"}),
            ("post", "/rpc/bridge/settlement/esc_x/refund", None),
            ("post", "/rpc/bridge/settlement/esc_x/extend-timeout", {"extension_seconds": 60}),
            ("post", "/rpc/bridge/settlement/esc_x/dispute", {"reason": "r"}),
            ("post", "/rpc/bridge/settlement/esc_x/resolve", {"resolution": "refund"}),
        ]:
            resp = getattr(client, method)(path, json=body, headers={"X-API-Key": "test-key-123"})
            assert resp.status_code == 410, f"{method} {path} → {resp.status_code}: {resp.text}"
            assert "retired" in resp.json()["detail"]
            assert "#2385" in resp.json()["detail"]

    def test_read_routes_reject_missing_key(self, client):
        for path in [
            "/rpc/bridge/settlement/esc_x",
            "/rpc/bridge/settlement/esc_x/status",
            "/rpc/bridge/settlement/esc_x/proofs",
        ]:
            resp = client.get(path)
            assert resp.status_code == 403, f"GET {path} → {resp.status_code}"

    def test_wrong_key_rejected(self, client):
        resp = client.post("/rpc/bridge/settlement/esc_x/refund", headers={"X-API-Key": "nope"})
        assert resp.status_code == 403

    def test_valid_key_reaches_handler(self, client):
        """With the key, the request passes auth and reaches the handler —
        mutating routes now answer the #2385 retired 410; a read route
        reaches the service layer (404/500 here depending on the test
        env's DB — anything but 403 proves auth ran)."""
        resp = client.post("/rpc/bridge/settlement/esc_x/refund", headers={"X-API-Key": "test-key-123"})
        assert resp.status_code == 410
        resp = client.get("/rpc/bridge/settlement/esc_x", headers={"X-API-Key": "test-key-123"})
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# SDK verify_proof_chain — verified locally, not by trusting the server
# ---------------------------------------------------------------------------


class TestClientProofChainVerification:
    """``client.verify_proof_chain`` previously returned ``data.get("valid",
    False)`` — the route never emits ``valid``/``errors``, so every chain
    reported invalid-with-no-reason. The SDK now runs
    ``aitbc.settlement.proofs.verify_proof_chain`` on the wire proofs."""

    def _wire(self, proof) -> dict:
        from aitbc.settlement.proofs import proof_to_dict

        return {"id": 1, "escrow_id": "e", **proof_to_dict(proof)}

    def _valid_chain(self) -> list[dict]:
        from aitbc.settlement.proofs import (
            build_execution_proof,
            build_lock_proof,
            build_release_proof,
            build_settlement_proof,
            build_verification_proof,
            compute_proof_hash,
        )

        lock = build_lock_proof("src", "0xl", 100, "alice", "bob", 10, "0xb10", timestamp=1.0)
        ver = build_verification_proof(
            "dst", "0xv", "e", 20, "0xb20", previous_proof_hash=compute_proof_hash(lock), timestamp=2.0
        )
        exe = build_execution_proof("dst", "0xx", "e", 21, "0xb21", previous_proof_hash=compute_proof_hash(ver), timestamp=3.0)
        rel = build_release_proof("dst", "0xr", "e", 22, "0xb22", previous_proof_hash=compute_proof_hash(exe), timestamp=4.0)
        stl = build_settlement_proof(
            "src", "0xs", "e", 11, "0xb11", previous_proof_hash=compute_proof_hash(rel), timestamp=5.0
        )
        return [self._wire(p) for p in (lock, ver, exe, rel, stl)]

    @pytest.mark.asyncio
    async def test_valid_chain_verifies(self):
        from unittest.mock import AsyncMock

        from aitbc.settlement.client import SettlementClient

        client = SettlementClient()
        client.get_proofs = AsyncMock(return_value={"escrow_id": "e", "proofs": self._valid_chain()})
        result = await client.verify_proof_chain("e")
        assert result == {"valid": True, "errors": []}

    @pytest.mark.asyncio
    async def test_tampered_chain_reports_errors(self):
        from unittest.mock import AsyncMock

        from aitbc.settlement.client import SettlementClient

        chain = self._valid_chain()
        chain[2]["tx_hash"] = "0xforged"  # breaks the hash link to proof 3
        client = SettlementClient()
        client.get_proofs = AsyncMock(return_value={"escrow_id": "e", "proofs": chain})
        result = await client.verify_proof_chain("e")
        assert result["valid"] is False
        assert any("previous_proof_hash" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_empty_chain_is_invalid(self):
        from unittest.mock import AsyncMock

        from aitbc.settlement.client import SettlementClient

        client = SettlementClient()
        client.get_proofs = AsyncMock(return_value={"escrow_id": "e", "proofs": []})
        result = await client.verify_proof_chain("e")
        assert result["valid"] is False
        assert result["errors"]

    def test_client_sends_api_key_from_env(self, monkeypatch):
        from aitbc.settlement.client import SettlementClient

        monkeypatch.setenv("BLOCKCHAIN_RPC_API_KEY", "env-key-9")
        client = SettlementClient()
        assert client._ensure_client().headers.get("x-api-key") == "env-key-9"
