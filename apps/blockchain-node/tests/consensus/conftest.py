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
