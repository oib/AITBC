"""V23-18: the execution timelock must fail closed.

The audit found that ``execute_proposal`` skipped the timelock entirely when a
proposal had no recorded ``block_height`` — which happens whenever the best-effort
GOVERNANCE_PROPOSE submission fails. Fixing that exposed the same shape one level
out: the check lived *inside* ``if settings.enable_onchain_submission``, and that
setting is False by default, so the shipped configuration executed every proposal
with no timelock at all.

These tests pin both, plus the cases where the delay simply cannot be proven.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from governance_service.config import settings
from governance_service.domain.governance import Proposal, ProposalStatus
from governance_service.services.governance_service import GovernanceService

# Heights used throughout. The chain is well past the proposal so that only the
# timelock arithmetic, not the ordering, decides each outcome.
PROPOSAL_BLOCK = 1_000
VOTING_PERIOD = 7_200
VOTING_ENDS_BLOCK = PROPOSAL_BLOCK + VOTING_PERIOD
TIMELOCK = 43_200


class StubBlockchain:
    """Blockchain client stub returning a fixed height, or raising."""

    def __init__(self, height: int | None = None, error: Exception | None = None):
        self._height = height
        self._error = error
        self.calls: list[str] = []

    async def get_block_height(self, chain_id: str) -> int:
        self.calls.append(chain_id)
        if self._error is not None:
            raise self._error
        assert self._height is not None
        return self._height


def make_proposal(
    *,
    block_height: int | None = PROPOSAL_BLOCK,
    voting_ends_block: int | None = VOTING_ENDS_BLOCK,
    proposal_type: str = "general",
    status: str = "succeeded",
) -> Proposal:
    now = datetime.now(UTC)
    return Proposal(
        proposal_id="prop_v23_18",
        title="t",
        description="d",
        proposer_id="prof_1",
        proposal_type=proposal_type,
        status=status,
        chain_id="ait-hub",
        block_height=block_height,
        voting_ends_block=voting_ends_block,
        voting_starts=now - timedelta(hours=8),
        voting_ends=now - timedelta(hours=4),
    )


def make_service(blockchain: StubBlockchain) -> GovernanceService:
    # _enforce_execution_timelock touches neither the session nor anything that
    # would, so None is honest here: passing a mock session would suggest the
    # method reads state it does not read.
    return GovernanceService(session=None, blockchain_client=blockchain)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _require_timelock(monkeypatch):
    """Every test runs with the safety control on unless it says otherwise."""
    monkeypatch.setattr(settings, "require_execution_timelock", True)
    monkeypatch.setattr(settings, "timelock_blocks", TIMELOCK)
    monkeypatch.setattr(settings, "voting_period_blocks", VOTING_PERIOD)


class TestTimelockCannotBeVerified:
    """Each missing input is a refusal, not an exemption. This is the V23-18 defect."""

    async def test_missing_block_height_is_refused(self):
        """The original defect: no block height used to mean no timelock."""
        service = make_service(StubBlockchain(height=10**9))
        proposal = make_proposal(block_height=None)

        with pytest.raises(ValueError, match="no on-chain block height"):
            await service._enforce_execution_timelock(proposal)

    async def test_missing_voting_ends_block_is_refused(self):
        """Proposals predating the voting_ends_block column must be re-submitted."""
        service = make_service(StubBlockchain(height=10**9))
        proposal = make_proposal(voting_ends_block=None)

        with pytest.raises(ValueError, match="no voting_ends_block"):
            await service._enforce_execution_timelock(proposal)

    async def test_unreachable_chain_is_refused(self):
        """An unreachable chain must not become a way to execute early."""
        blockchain = StubBlockchain(error=ConnectionError("connection refused"))
        service = make_service(blockchain)

        with pytest.raises(ValueError, match="unreachable"):
            await service._enforce_execution_timelock(make_proposal())

    async def test_refusal_does_not_depend_on_reaching_the_chain(self):
        """A proposal with no height is refused without an RPC round trip."""
        blockchain = StubBlockchain(height=10**9)
        service = make_service(blockchain)

        with pytest.raises(ValueError):
            await service._enforce_execution_timelock(make_proposal(block_height=None))

        assert blockchain.calls == []


class TestTimelockArithmetic:
    async def test_refused_one_block_early(self):
        service = make_service(StubBlockchain(height=VOTING_ENDS_BLOCK + TIMELOCK - 1))

        with pytest.raises(ValueError, match="Timelock not expired"):
            await service._enforce_execution_timelock(make_proposal())

    async def test_allowed_exactly_at_expiry(self):
        service = make_service(StubBlockchain(height=VOTING_ENDS_BLOCK + TIMELOCK))

        await service._enforce_execution_timelock(make_proposal())  # does not raise

    async def test_measured_from_voting_end_not_proposal_creation(self):
        """The window follows the voting period rather than overlapping it.

        At this height the timelock has elapsed when measured from proposal
        creation, but not from the end of voting. The old code measured from
        creation and would have allowed execution here.
        """
        height = PROPOSAL_BLOCK + TIMELOCK + 1
        assert height - PROPOSAL_BLOCK >= TIMELOCK  # old measurement: expired
        assert height - VOTING_ENDS_BLOCK < TIMELOCK  # correct measurement: not yet

        service = make_service(StubBlockchain(height=height))
        with pytest.raises(ValueError, match="Timelock not expired"):
            await service._enforce_execution_timelock(make_proposal())


class TestEmergencyFastTrack:
    async def test_emergency_uses_accelerated_timelock(self, monkeypatch):
        monkeypatch.setattr(settings, "emergency_timelock_blocks", 7_200)
        height = VOTING_ENDS_BLOCK + 7_200

        service = make_service(StubBlockchain(height=height))
        await service._enforce_execution_timelock(make_proposal(proposal_type="emergency"))

        # The same height is still too early for a normal proposal.
        service = make_service(StubBlockchain(height=height))
        with pytest.raises(ValueError, match="need 43200"):
            await service._enforce_execution_timelock(make_proposal(proposal_type="general"))

    async def test_emergency_refusal_says_it_is_a_fast_track(self, monkeypatch):
        """The message distinguishes the two timelocks, so 'not expired' is diagnosable."""
        monkeypatch.setattr(settings, "emergency_timelock_blocks", 7_200)
        service = make_service(StubBlockchain(height=VOTING_ENDS_BLOCK + 7_199))

        with pytest.raises(ValueError, match="emergency fast-track"):
            await service._enforce_execution_timelock(make_proposal(proposal_type="emergency"))


class TestBypassIsExplicitAndLoud:
    async def test_bypass_requires_the_setting_and_logs(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "require_execution_timelock", False)
        service = make_service(StubBlockchain(error=AssertionError("must not be called")))

        with caplog.at_level("WARNING"):
            await service._enforce_execution_timelock(make_proposal(block_height=None))

        assert "BYPASSED" in caplog.text
        assert "prop_v23_18" in caplog.text


# ---------------------------------------------------------------------------
# The enclosing fail-open: the check used to sit inside the on-chain branch
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


def _submit_returning(**result):
    async def _submit(**kwargs):
        return result

    return _submit


class StubSession:
    def __init__(self, proposal: Proposal):
        self._proposal = proposal
        self.added: list = []

    async def execute(self, stmt):
        return _Result([self._proposal])

    def add(self, record):
        self.added.append(record)

    async def commit(self):
        pass

    async def refresh(self, record):
        pass


class TestMigration003:
    """Mirrors the v0.7.3 convention in test_v073_governance.py."""

    def test_migration_file_exists_and_chains_to_002(self):
        import importlib.util
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "003_v023_voting_ends_block.py"
        assert migration_path.exists()
        spec = importlib.util.spec_from_file_location("migration_003", migration_path)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "003"
        assert mod.down_revision == "002"
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)


class TestCreateProposalRecordsVotingEnd:
    """The producer side. The HTLC lesson: check what writes the quantity, not only what reads it."""

    async def test_voting_ends_block_is_recorded_from_the_on_chain_height(self, monkeypatch):
        monkeypatch.setattr(settings, "enable_onchain_submission", True)
        monkeypatch.setattr(settings, "proposer_private_key", "0x" + "11" * 32)

        blockchain = StubBlockchain(height=PROPOSAL_BLOCK)
        blockchain.submit_governance_tx = _submit_returning(  # type: ignore[attr-defined]
            tx_hash="0xpropose", block_height=PROPOSAL_BLOCK
        )
        session = StubSession(None)  # type: ignore[arg-type]
        service = GovernanceService(session=session, blockchain_client=blockchain)  # type: ignore[arg-type]

        proposal = await service.create_proposal(
            {"title": "t", "description": "d", "proposer_id": "prof_1", "proposal_type": "general"}
        )

        assert proposal.block_height == PROPOSAL_BLOCK
        assert proposal.voting_ends_block == PROPOSAL_BLOCK + VOTING_PERIOD

    async def test_failed_submission_leaves_no_heights_and_so_blocks_execution(self, monkeypatch):
        """The V23-18 entry point: a best-effort failure must not yield a timelock-free proposal."""
        monkeypatch.setattr(settings, "enable_onchain_submission", True)
        monkeypatch.setattr(settings, "proposer_private_key", "0x" + "11" * 32)

        async def _fail(**kwargs):
            raise ConnectionError("rpc down")

        blockchain = StubBlockchain(height=PROPOSAL_BLOCK)
        blockchain.submit_governance_tx = _fail  # type: ignore[attr-defined]
        service = GovernanceService(session=StubSession(None), blockchain_client=blockchain)  # type: ignore[arg-type]

        proposal = await service.create_proposal(
            {"title": "t", "description": "d", "proposer_id": "prof_1", "proposal_type": "general"}
        )

        # Creation still succeeds — on-chain submission is best-effort by design.
        assert proposal.block_height is None
        assert proposal.voting_ends_block is None

        # But the proposal is now unexecutable rather than timelock-free.
        proposal.status = "succeeded"
        with pytest.raises(ValueError, match="Cannot verify timelock"):
            await service._enforce_execution_timelock(proposal)


class TestExecuteProposalEnforcesTimelockOffChain:
    """With on-chain submission off — the shipped default — the timelock still applies."""

    async def test_offchain_execution_is_refused_without_a_verifiable_timelock(self, monkeypatch):
        monkeypatch.setattr(settings, "enable_onchain_submission", False)
        monkeypatch.setattr(settings, "proposer_private_key", "")

        proposal = make_proposal(block_height=None)
        session = StubSession(proposal)
        service = GovernanceService(session=session, blockchain_client=StubBlockchain(height=10**9))  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Cannot verify timelock"):
            await service.execute_proposal("prop_v23_18")

        assert proposal.status != ProposalStatus.EXECUTED
        assert proposal.executed_at is None

    async def test_refusal_is_recorded_in_the_execution_log(self, monkeypatch):
        """A refused execution leaves a trace — governance needs the audit trail."""
        monkeypatch.setattr(settings, "enable_onchain_submission", False)

        proposal = make_proposal(block_height=None)
        session = StubSession(proposal)
        service = GovernanceService(session=session, blockchain_client=StubBlockchain(height=10**9))  # type: ignore[arg-type]

        with pytest.raises(ValueError):
            await service.execute_proposal("prop_v23_18")

        logs = [r for r in session.added if hasattr(r, "execution_step")]
        assert len(logs) == 1
        assert logs[0].status == "failed"
        assert "Cannot verify timelock" in logs[0].error_message

    async def test_execution_records_its_height_without_erasing_the_creation_height(self, monkeypatch):
        """block_height is the evidence the timelock check reads; execution must not overwrite it."""
        monkeypatch.setattr(settings, "enable_onchain_submission", True)
        monkeypatch.setattr(settings, "proposer_private_key", "0x" + "11" * 32)

        proposal = make_proposal()
        session = StubSession(proposal)
        blockchain = StubBlockchain(height=VOTING_ENDS_BLOCK + TIMELOCK)
        blockchain.submit_governance_tx = _submit_returning(tx_hash="0xexec", block_height=999_999)  # type: ignore[attr-defined]
        service = GovernanceService(session=session, blockchain_client=blockchain)  # type: ignore[arg-type]

        await service.execute_proposal("prop_v23_18", executor_address="0xexecutor")

        assert proposal.block_height == PROPOSAL_BLOCK  # creation height preserved
        assert proposal.execution_tx_hash == "0xexec"
        assert proposal.proposal_metadata["execution_block_height"] == 999_999

    async def test_offchain_execution_proceeds_once_the_timelock_is_provable(self, monkeypatch):
        monkeypatch.setattr(settings, "enable_onchain_submission", False)

        proposal = make_proposal()
        session = StubSession(proposal)
        blockchain = StubBlockchain(height=VOTING_ENDS_BLOCK + TIMELOCK)
        service = GovernanceService(session=session, blockchain_client=blockchain)  # type: ignore[arg-type]

        result = await service.execute_proposal("prop_v23_18")

        assert result is not None
        assert proposal.status == ProposalStatus.EXECUTED
