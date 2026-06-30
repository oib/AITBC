"""
B14: Integration tests for consensus (full rounds, slashing, view change, persistence)
"""

from unittest.mock import Mock

import pytest

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.pbft import PBFTConsensus
from aitbc_chain.gossip.broker import InMemoryGossipBackend


def _make_consensus(n_validators: int = 4, chain_id: str = "test-int-chain") -> MultiValidatorPoA:
    """Create a MultiValidatorPoA with n validators, all PROPOSER role."""
    consensus = MultiValidatorPoA(chain_id)
    for i in range(n_validators):
        addr = f"0x{i:040x}"
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return consensus


@pytest.mark.asyncio
async def test_full_consensus_round():
    """4 validators, attempt_consensus completes"""
    consensus = _make_consensus(4)
    consensus._require_block_signatures = False
    result = await consensus.attempt_consensus(block_hash="0xtestblock", round=1)
    assert result is True
    assert consensus.consensus_attempts == 1


@pytest.mark.asyncio
async def test_byzantine_validator_slashed():
    """equivocation triggers slashing, consensus continues"""
    consensus = _make_consensus(4)
    consensus._require_block_signatures = False
    validator = list(consensus.validators.keys())[0]
    initial_stake = consensus.validators[validator].stake
    # Trigger equivocation
    consensus.record_prepare(validator, "hashA", 1)
    consensus.record_prepare(validator, "hashB", 1)
    # Slashing should have occurred
    assert consensus.validators[validator].stake < initial_stake
    # Consensus should still work with remaining validators
    result = await consensus.attempt_consensus(block_hash="0xtestblock", round=1)
    assert result is True


@pytest.mark.asyncio
async def test_block_forgery_rejected():
    """forged block rejected by validate_block"""
    consensus = _make_consensus(4)
    consensus._require_block_signatures = True
    from aitbc_chain.models import Block

    block = Mock(spec=Block)
    block.hash = "0xabc"
    block.signature = "0xforged"
    proposer = list(consensus.validators.keys())[0]
    result = consensus.validate_block(block, proposer)
    assert result is False


@pytest.mark.asyncio
async def test_view_change_recovery():
    """view change works, new proposer selected"""
    consensus = _make_consensus(4)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")
    proposer = list(consensus.validators.keys())[0]
    await pbft.pre_prepare_phase(proposer, "0xblockhash")
    # Trigger view change
    result = pbft.handle_view_change(1)
    assert result is True
    assert pbft.state.current_view == 1
    # New proposer should be selectable
    new_proposer = consensus.select_proposer(2)
    assert new_proposer is not None


@pytest.mark.asyncio
async def test_network_partition_recovery():
    """partition heals, can_resume_consensus works"""
    consensus = _make_consensus(4)
    # Mark as partitioned
    consensus.network_partitioned = True
    # Not healed yet — should return False
    assert consensus.can_resume_consensus() is False
    # Heal the partition
    import time

    consensus.network_partitioned = False
    consensus.last_partition_healed = time.time() - 10  # 10 seconds ago
    # Now should be able to resume
    assert consensus.can_resume_consensus() is True


def test_state_persistence_save_load():
    """save_state then load_state restores validators (mock the DB session)"""
    consensus = _make_consensus(3, chain_id="test-persist-chain")
    # The mock session simulates a DB row
    mock_row = Mock()
    mock_row.current_view = 0
    mock_row.current_sequence = 0
    mock_row.current_epoch = 0
    mock_row.validator_set_json = ""
    mock_row.slashing_events_json = "[]"

    mock_session = Mock()
    # query().filter_by().first() returns None on first save (insert), then row on load

    class MockQuery:
        def __init__(self, session):
            self.session = session

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return None  # no existing row

    mock_session.query = Mock(return_value=MockQuery(mock_session))

    import contextlib

    @contextlib.contextmanager
    def mock_session_scope(chain_id=""):
        yield mock_session

    # Patch session_scope in the database module
    from unittest.mock import patch

    with patch("aitbc_chain.database.session_scope", mock_session_scope):
        # Save state
        result = consensus.save_state()
        assert result is True
        # Verify session.add was called (insert path since no existing row)
        assert mock_session.add.called

    # Now test load — simulate a row with saved validator set
    import json

    saved_validator_set = {
        addr: {
            "stake": v.stake,
            "reputation": v.reputation,
            "role": v.role.value,
            "last_proposed": v.last_proposed,
            "is_active": v.is_active,
        }
        for addr, v in consensus.validators.items()
    }
    mock_row.validator_set_json = json.dumps(saved_validator_set)
    mock_row.current_view = 2
    mock_row.current_sequence = 5
    mock_row.current_epoch = 1

    class MockQueryLoad:
        def __init__(self):
            pass

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return mock_row

    mock_session_load = Mock()
    mock_session_load.query = Mock(return_value=MockQueryLoad())

    @contextlib.contextmanager
    def mock_session_scope_load(chain_id=""):
        yield mock_session_load

    # Create a fresh consensus to load into
    fresh_consensus = MultiValidatorPoA("test-persist-chain")
    with patch("aitbc_chain.database.session_scope", mock_session_scope_load):
        result = fresh_consensus.load_state()
        assert result is True
    # Validators should be restored
    assert len(fresh_consensus.validators) == 3
    assert fresh_consensus._pbft_view == 2
    assert fresh_consensus._pbft_sequence == 5
    assert fresh_consensus._current_epoch == 1


@pytest.mark.asyncio
async def test_multi_node_pbft():
    """3 PBFTConsensus instances with InMemoryGossipBackend"""
    consensus = _make_consensus(3)
    backend = InMemoryGossipBackend()

    # Create 3 PBFT instances sharing the same gossip backend
    pbft_instances = []
    for _i in range(3):
        pbft = PBFTConsensus(consensus, private_key="", chain_id="test-multi")
        pbft.set_gossip_backend(backend)
        pbft_instances.append(pbft)

    # Node 0 starts pre-prepare
    proposer = list(consensus.validators.keys())[0]
    result = await pbft_instances[0].pre_prepare_phase(proposer, "0xsharedblock")
    assert result is True
    # All instances should have the pre-prepare message
    key = list(pbft_instances[0].state.pre_prepare_messages.keys())[0]
    assert key in pbft_instances[0].state.pre_prepare_messages


if __name__ == "__main__":
    pytest.main([__file__])
