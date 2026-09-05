"""Local-state divergence detection in the block-import state-root check.

Regression cover for the hub2 incident of 2026-09-05: the node held one account
row one transaction ahead of its own head, so every attempt to import the next
block re-applied a transaction the state already contained and could never
reproduce the expected root. It logged 866 identical "State root mismatch ...
BLOCK REJECTED" lines over six hours, all of which pointed at the incoming
block, while the fault was entirely local.
"""

import pytest
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Account, Block
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state import state_root_utils
from aitbc_chain.sync_block_import import BlockImportMixin

CHAIN_ID = "test-chain"
ADDRESS = "0xd3d4362840AC0727EEC41570b0b69CF8313E740B"


class _Importer:
    """Minimal stand-in: the helper only reads ``self._chain_id``."""

    _chain_id = CHAIN_ID

    describe = BlockImportMixin._describe_local_state_divergence


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN_ID, address=ADDRESS, balance=3172029541, nonce=63))
        s.commit()
        yield s


def _add_head(session, state_root):
    session.add(
        Block(
            chain_id=CHAIN_ID,
            height=1299,
            hash="0x" + "11" * 32,
            parent_hash="0x" + "22" * 32,
            proposer=ADDRESS,
            state_root=state_root,
        )
    )
    session.commit()


def test_no_divergence_when_state_matches_head(session):
    """State that hashes to the head's recorded root is not a local fault."""
    _add_head(session, state_root_utils.compute_state_root_full(session, CHAIN_ID))

    assert _Importer().describe(session, 1299) is None


def test_divergence_detected_when_state_ran_ahead_of_head(session):
    """One account advanced past the head is reported as a local divergence."""
    _add_head(session, state_root_utils.compute_state_root_full(session, CHAIN_ID))

    # Exactly the hub2 drift: one transaction's fee and nonce applied to the
    # account without the corresponding block ever being recorded.
    account = session.get(Account, (CHAIN_ID, ADDRESS))
    account.balance -= 360000
    account.nonce += 1
    session.add(account)
    session.commit()

    described = _Importer().describe(session, 1299)

    assert described is not None
    assert "head records state root" in described
    assert "our accounts hash to" in described


def test_no_head_block_is_not_reported_as_divergence(session):
    """Without a parent block there is nothing to compare against."""
    assert _Importer().describe(session, 1299) is None
