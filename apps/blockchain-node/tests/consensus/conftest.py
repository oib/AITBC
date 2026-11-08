"""Conftest for consensus tests (v0.7.5).

Enables ``multi_validator_consensus_enabled`` so the RuntimeError guards
in ``MultiValidatorPoA`` and ``PBFTConsensus`` do not fire during tests.
"""

import sys
from pathlib import Path

import pytest

# Ensure the blockchain-node source is importable
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aitbc_chain.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def enable_multi_validator_consensus():
    """Enable multi-validator consensus for all consensus tests."""
    original = settings.multi_validator_consensus_enabled
    settings.multi_validator_consensus_enabled = True
    yield
    settings.multi_validator_consensus_enabled = original


@pytest.fixture(autouse=True)
def disable_pbft_signature_requirement():
    """Accept unsigned PBFT messages in tests (v0.18.0 flag, explicit opt-out)."""
    original = settings.pbft_require_signatures
    settings.pbft_require_signatures = False
    yield
    settings.pbft_require_signatures = original


@pytest.fixture(autouse=True)
def _isolate_persisted_vote_state():
    """#1268: ``attestation_signed.json`` and ``vote_journal.json`` persist by
    design and the journal is a process-wide registry; without cleanup a vote
    written by one test is a prior vote for the next test sharing the chain_id.
    Same isolation A's held d92990dc6 added for attestation_signed.json."""
    from aitbc.constants import DATA_DIR
    from aitbc_chain.consensus import vote_fetch, vote_journal

    def _scrub() -> None:
        data_dir = Path(DATA_DIR) / "data"
        if data_dir.exists():
            for pattern in ("*/attestation_signed.json*", "*/vote_journal.json*"):
                for stale in data_dir.glob(pattern):
                    stale.unlink(missing_ok=True)
        vote_journal.reset_vote_journals()
        vote_fetch.reset_throttle()

    _scrub()
    yield
    _scrub()
