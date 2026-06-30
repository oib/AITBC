"""
B14: Tests for PBFT Consensus (C4, C5, H4, H5, H6)
"""

import pytest

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.pbft import (
    PBFTConsensus,
    PBFTMessage,
    PBFTMessageType,
)


def _make_consensus(n_validators: int = 4) -> MultiValidatorPoA:
    """Create a MultiValidatorPoA with n validators, all PROPOSER role."""
    consensus = MultiValidatorPoA("test-pbft-chain")
    for i in range(n_validators):
        addr = f"0x{i:040x}"
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return consensus


@pytest.mark.asyncio
async def test_pre_prepare_creates_message():
    """pre_prepare_phase creates a message in pre_prepare_messages"""
    consensus = _make_consensus(4)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")
    proposer = list(consensus.validators.keys())[0]
    result = await pbft.pre_prepare_phase(proposer, "0xblockhash")
    assert result is True
    # A pre-prepare message should be stored
    assert len(pbft.state.pre_prepare_messages) == 1
    key = list(pbft.state.pre_prepare_messages.keys())[0]
    msg = pbft.state.pre_prepare_messages[key]
    assert msg.message_type == PBFTMessageType.PRE_PREPARE
    assert msg.sender == proposer
    assert msg.digest != ""


@pytest.mark.asyncio
async def test_prepare_accumulates_messages():
    """prepare_phase adds to prepared_messages"""
    consensus = _make_consensus(4)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")
    proposer = list(consensus.validators.keys())[0]
    await pbft.pre_prepare_phase(proposer, "0xblockhash")
    key = list(pbft.state.pre_prepare_messages.keys())[0]
    pre_prepare_msg = pbft.state.pre_prepare_messages[key]
    # Send a prepare from a different validator
    validator = list(consensus.validators.keys())[1]
    result = await pbft.prepare_phase(validator, pre_prepare_msg)
    # One message is not enough for quorum (need 2f+1=3)
    assert len(pbft.state.prepared_messages[key]) == 1
    # result is False because quorum not yet reached
    assert result is False


@pytest.mark.asyncio
async def test_commit_accumulates_messages():
    """commit_phase adds to committed_messages"""
    consensus = _make_consensus(4)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")
    proposer = list(consensus.validators.keys())[0]
    await pbft.pre_prepare_phase(proposer, "0xblockhash")
    key = list(pbft.state.pre_prepare_messages.keys())[0]
    pre_prepare_msg = pbft.state.pre_prepare_messages[key]
    validator = list(consensus.validators.keys())[1]
    await pbft.prepare_phase(validator, pre_prepare_msg)
    prepare_msg = pbft.state.prepared_messages[key][0]
    result = await pbft.commit_phase(validator, prepare_msg)
    # One commit is not enough for quorum
    assert len(pbft.state.committed_messages[key]) == 1
    assert result is False


@pytest.mark.asyncio
async def test_reject_unsigned_message_when_key_set():
    """when private_key is set, unsigned incoming messages are rejected"""
    consensus = _make_consensus(4)
    # Use a dummy private key (non-empty) to enable signing mode
    pbft = PBFTConsensus(consensus, private_key="a" * 64, chain_id="test")
    # Create an unsigned message
    msg = PBFTMessage(
        message_type=PBFTMessageType.PREPARE,
        sender="0xabc",
        view_number=0,
        sequence_number=1,
        digest="0xdigest",
        signature="",  # unsigned
        timestamp=0.0,
    )
    # _verify_message_signature should reject unsigned messages when key is set
    assert pbft._verify_message_signature(msg) is False


@pytest.mark.asyncio
async def test_quorum_reached():
    """with 4 validators, 2f+1=3 prepare messages needed"""
    consensus = _make_consensus(4)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")
    # 4 validators → f = 4//3 = 1 → required = 2*1+1 = 3
    assert pbft.fault_tolerance == 1
    assert pbft.required_messages == 3

    proposer = list(consensus.validators.keys())[0]
    await pbft.pre_prepare_phase(proposer, "0xblockhash")
    key = list(pbft.state.pre_prepare_messages.keys())[0]
    pre_prepare_msg = pbft.state.pre_prepare_messages[key]

    validators = list(consensus.validators.keys())
    # Send 2 prepares — not enough
    result1 = await pbft.prepare_phase(validators[1], pre_prepare_msg)
    assert result1 is False
    result2 = await pbft.prepare_phase(validators[2], pre_prepare_msg)
    assert result2 is False
    # 3rd prepare — quorum reached
    result3 = await pbft.prepare_phase(validators[3], pre_prepare_msg)
    assert result3 is True
    assert len(pbft.state.prepared_messages[key]) == 3


@pytest.mark.asyncio
async def test_dynamic_fault_tolerance():
    """adding validators changes fault_tolerance"""
    consensus = _make_consensus(3)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")
    # 3 validators → f = 1 → required = 3
    assert pbft.fault_tolerance == 1
    assert pbft.required_messages == 3

    # Add more validators (need 7+ for f=2)
    for i in range(3, 7):
        addr = f"0x{i:040x}"
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER

    # Trigger recalculation via pre_prepare_phase
    proposer = list(consensus.validators.keys())[0]
    await pbft.pre_prepare_phase(proposer, "0xblockhash")
    # 7 validators → f = 7//3 = 2 → required = 5
    assert pbft.fault_tolerance == 2
    assert pbft.required_messages == 5


@pytest.mark.asyncio
async def test_view_change_preserves_committed():
    """after view change, committed_messages not cleared"""
    consensus = _make_consensus(4)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")
    proposer = list(consensus.validators.keys())[0]
    await pbft.pre_prepare_phase(proposer, "0xblockhash")
    key = list(pbft.state.pre_prepare_messages.keys())[0]
    pre_prepare_msg = pbft.state.pre_prepare_messages[key]
    validator = list(consensus.validators.keys())[1]
    await pbft.prepare_phase(validator, pre_prepare_msg)
    prepare_msg = pbft.state.prepared_messages[key][0]
    await pbft.commit_phase(validator, prepare_msg)
    # Advance sequence to simulate committed state
    pbft.state.current_sequence = 1
    # Trigger view change
    result = pbft.handle_view_change(1)
    assert result is True
    # committed_messages for seq 1 should be preserved (seq <= current_sequence)
    assert key in pbft.state.committed_messages


@pytest.mark.asyncio
async def test_view_change_clears_uncommitted():
    """after view change, uncommitted prepared_messages cleared"""
    consensus = _make_consensus(4)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")
    proposer = list(consensus.validators.keys())[0]
    await pbft.pre_prepare_phase(proposer, "0xblockhash")
    key = list(pbft.state.pre_prepare_messages.keys())[0]
    pre_prepare_msg = pbft.state.pre_prepare_messages[key]
    validator = list(consensus.validators.keys())[1]
    await pbft.prepare_phase(validator, pre_prepare_msg)
    # current_sequence is still 0, so seq 1 is uncommitted
    # Trigger view change
    result = pbft.handle_view_change(1)
    assert result is True
    # prepared_messages for uncommitted seq should be cleared
    assert key not in pbft.state.prepared_messages
    assert key not in pbft.state.pre_prepare_messages


@pytest.mark.asyncio
async def test_gossip_transport_publishes():
    """with a mock gossip backend, messages are published"""
    consensus = _make_consensus(4)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")

    published = []

    class MockBackend:
        async def publish(self, topic, message):
            published.append((topic, message))

    pbft.set_gossip_backend(MockBackend())
    proposer = list(consensus.validators.keys())[0]
    await pbft.pre_prepare_phase(proposer, "0xblockhash")
    # Messages should have been published to all validators except sender
    assert len(published) > 0
    # Check topic format
    topic, msg_data = published[0]
    assert "pre_prepare" in topic
    assert msg_data["message_type"] == "pre_prepare"


@pytest.mark.asyncio
async def test_gossip_transport_receives():
    """handle_incoming_message routes messages correctly"""
    consensus = _make_consensus(4)
    pbft = PBFTConsensus(consensus, private_key="", chain_id="test")

    # Simulate an incoming prepare message
    msg_data = {
        "message_type": "prepare",
        "sender": "0xabc",
        "view_number": 0,
        "sequence_number": 1,
        "digest": "0xdigest",
        "signature": "",
        "timestamp": 0.0,
    }
    pbft.handle_incoming_message(msg_data)
    key = "1:0"
    assert key in pbft.state.prepared_messages
    assert len(pbft.state.prepared_messages[key]) == 1

    # Simulate an incoming pre-prepare message
    pp_data = {
        "message_type": "pre_prepare",
        "sender": "0xdef",
        "view_number": 0,
        "sequence_number": 2,
        "digest": "0xdigest2",
        "signature": "",
        "timestamp": 0.0,
    }
    pbft.handle_incoming_message(pp_data)
    assert "2:0" in pbft.state.pre_prepare_messages

    # Simulate an incoming commit message
    commit_data = {
        "message_type": "commit",
        "sender": "0xghi",
        "view_number": 0,
        "sequence_number": 1,
        "digest": "0xdigest",
        "signature": "",
        "timestamp": 0.0,
    }
    pbft.handle_incoming_message(commit_data)
    assert key in pbft.state.committed_messages
    assert len(pbft.state.committed_messages[key]) == 1


if __name__ == "__main__":
    pytest.main([__file__])
