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
async def test_reject_unsigned_message_when_signatures_required():
    """unsigned incoming messages are rejected when pbft_require_signatures is on"""
    from aitbc_chain.config import settings

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
    original = settings.pbft_require_signatures
    settings.pbft_require_signatures = True
    try:
        assert pbft._verify_message_signature(msg) is False
    finally:
        settings.pbft_require_signatures = original


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
    from aitbc_chain.config import settings

    # Disable the attestation minimum so this test exercises pure BFT thresholds.
    original_min = settings.multi_validator_min_attestations
    settings.multi_validator_min_attestations = 0
    try:
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
    finally:
        settings.multi_validator_min_attestations = original_min


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
    await pbft.handle_incoming_message(msg_data)
    key = "1:0"
    assert key in pbft.state.prepared_messages
    assert len(pbft.state.prepared_messages[key]) == 1

    # Simulate an incoming pre-prepare message. The sender has to be the
    # validator the schedule picks for that height and round, otherwise the
    # pre-prepare is dropped as out of turn (v0.25.6).
    pp_data = {
        "message_type": "pre_prepare",
        "sender": consensus.select_proposer(2, 0),
        "view_number": 0,
        "sequence_number": 2,
        "digest": "0xdigest2",
        "signature": "",
        "timestamp": 0.0,
    }
    await pbft.handle_incoming_message(pp_data)
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
    await pbft.handle_incoming_message(commit_data)
    assert key in pbft.state.committed_messages
    assert len(pbft.state.committed_messages[key]) == 1


if __name__ == "__main__":
    pytest.main([__file__])


@pytest.mark.asyncio
async def test_four_validator_round():
    """A full PBFT round with 4 validators in memory reaches commit."""
    from eth_keys import keys
    import secrets

    class Network:
        def __init__(self, nodes):
            self.nodes = nodes

        async def publish(self, topic, msg_data):
            for node in self.nodes:
                if node._local_validator != msg_data["sender"]:
                    await node.handle_incoming_message(msg_data)

    # 4 independent validators
    validators: list[tuple[str, str, PBFTConsensus]] = []
    for _ in range(4):
        pk = keys.PrivateKey(secrets.token_bytes(32))
        addr = pk.public_key.to_checksum_address()
        validators.append((addr, pk.to_hex(), None))

    shared_consensus = MultiValidatorPoA("test-pbft-round")
    for addr, _, _ in validators:
        shared_consensus.add_validator(addr, 1000.0)
        shared_consensus.validators[addr].role = ValidatorRole.PROPOSER

    net = Network([])
    for i, (addr, pk_hex, _) in enumerate(validators):
        node = PBFTConsensus(shared_consensus, private_key=pk_hex, chain_id="test-pbft-round", local_validator=addr)
        node.set_gossip_backend(net)
        validators[i] = (addr, pk_hex, node)
        net.nodes.append(node)

    # The proposer has to be the validator the schedule picks for the height
    # and round; the addresses are random keys, so it is not validators[0].
    proposer_addr = shared_consensus.select_proposer(1, 0)
    proposer = next(node for addr, _, node in validators if addr == proposer_addr)
    block_hash = "0x" + secrets.token_hex(32)
    result = await proposer.propose_and_wait(proposer_addr, block_hash, timeout=5.0, sequence=1, view=0)
    assert result is True

    key = f"{proposer.state.current_sequence}:{proposer.state.current_view}"
    assert len(proposer.state.committed_messages.get(key, [])) >= proposer.required_messages


@pytest.mark.asyncio
async def test_fault_tolerance_with_one_validator_down():
    """A full PBFT round reaches commit even when one non-proposer validator is down.

    With 4 validators the BFT threshold is f=1 and required_messages=2f+1=3.
    The proposer sends pre-prepare, one validator is unresponsive, and the
    remaining two validators respond. The proposer plus those two gives the
    prepare and commit quorums, so the round completes.
    """
    from eth_keys import keys
    import secrets

    class FaultyNetwork:
        def __init__(self, nodes, down_index: int):
            self.nodes = nodes
            self.down_index = down_index

        async def publish(self, topic, msg_data):
            for i, node in enumerate(self.nodes):
                if i == self.down_index:
                    continue  # stopped validator receives nothing
                if node._local_validator != msg_data["sender"]:
                    await node.handle_incoming_message(msg_data)

    # 4 independent validators
    validators: list[tuple[str, str, PBFTConsensus]] = []
    for _ in range(4):
        pk = keys.PrivateKey(secrets.token_bytes(32))
        addr = pk.public_key.to_checksum_address()
        validators.append((addr, pk.to_hex(), None))

    shared_consensus = MultiValidatorPoA("test-pbft-faulty")
    for addr, _, _ in validators:
        shared_consensus.add_validator(addr, 1000.0)
        shared_consensus.validators[addr].role = ValidatorRole.PROPOSER

    # The proposer is whoever the schedule picks for height 1, round 0; the
    # stopped node must be one of the others.
    proposer_addr = shared_consensus.select_proposer(1, 0)
    down_index = next(i for i, (addr, _, _) in enumerate(validators) if addr != proposer_addr)

    net = FaultyNetwork([], down_index=down_index)
    for i, (addr, pk_hex, _) in enumerate(validators):
        node = PBFTConsensus(shared_consensus, private_key=pk_hex, chain_id="test-pbft-faulty", local_validator=addr)
        node.set_gossip_backend(net)
        validators[i] = (addr, pk_hex, node)
        net.nodes.append(node)

    proposer = next(node for addr, _, node in validators if addr == proposer_addr)
    block_hash = "0x" + secrets.token_hex(32)
    result = await proposer.propose_and_wait(proposer_addr, block_hash, timeout=5.0, sequence=1, view=0)
    assert result is True
    key = f"{proposer.state.current_sequence}:{proposer.state.current_view}"
    assert len(proposer.state.committed_messages.get(key, [])) >= proposer.required_messages

    # The stopped node must not have any committed messages for this key
    stopped = validators[net.down_index][2]
    assert len(stopped.state.committed_messages.get(key, [])) == 0


@pytest.mark.asyncio
async def test_round_one_proposer_takes_over_when_scheduled_proposer_is_down():
    """The whole point of the round: a dead round-0 proposer must not stall the height.

    Round 0 belongs to a validator whose host is gone, so it never sends a
    pre-prepare. The round-1 proposer, which every node derives from the parent
    block timestamp without exchanging any view-change message, proposes the
    same height and reaches a commit quorum with the three live validators.
    """
    from eth_keys import keys
    import secrets

    class Network:
        def __init__(self):
            self.nodes: list[PBFTConsensus] = []
            self.down: set[str] = set()

        async def publish(self, topic, msg_data):
            for node in self.nodes:
                if node._local_validator in self.down:
                    continue
                if node._local_validator != msg_data["sender"]:
                    await node.handle_incoming_message(msg_data)

    keypairs = []
    for _ in range(4):
        pk = keys.PrivateKey(secrets.token_bytes(32))
        keypairs.append((pk.public_key.to_checksum_address(), pk.to_hex()))

    shared_consensus = MultiValidatorPoA("test-pbft-rotate")
    for addr, _ in keypairs:
        shared_consensus.add_validator(addr, 1000.0)
        shared_consensus.validators[addr].role = ValidatorRole.PROPOSER

    height = 7
    dead = shared_consensus.select_proposer(height, 0)
    standin = shared_consensus.select_proposer(height, 1)
    assert dead != standin

    net = Network()
    net.down.add(dead)
    nodes: dict[str, PBFTConsensus] = {}
    for addr, pk_hex in keypairs:
        node = PBFTConsensus(shared_consensus, private_key=pk_hex, chain_id="test-pbft-rotate", local_validator=addr)
        node.set_gossip_backend(net)
        net.nodes.append(node)
        nodes[addr] = node

    block_hash = "0x" + secrets.token_hex(32)
    result = await nodes[standin].propose_and_wait(standin, block_hash, timeout=5.0, sequence=height, view=1)
    assert result is True, "round 1 proposer could not commit while round 0 proposer was down"


@pytest.mark.asyncio
async def test_out_of_turn_pre_prepare_is_dropped():
    """A validator that is not the scheduled proposer gets no prepares."""
    consensus = _make_consensus(4)
    height, view = 5, 0
    scheduled = consensus.select_proposer(height, view)
    impostor = next(a for a in consensus.validators if a != scheduled)

    pbft = PBFTConsensus(consensus, private_key="", chain_id="test", local_validator=scheduled)
    await pbft.handle_incoming_message(
        {
            "message_type": "pre_prepare",
            "sender": impostor,
            "view_number": view,
            "sequence_number": height,
            "digest": "0xdigest",
            "signature": "",
            "timestamp": 0.0,
            "block_hash": "0x" + "11" * 32,
        }
    )
    assert f"{height}:{view}" not in pbft.state.pre_prepare_messages
    assert not pbft.state.prepared_messages


@pytest.mark.asyncio
async def test_only_one_block_prepared_per_height():
    """Two proposals for one height, in different rounds, must not both be prepared.

    Otherwise the round-0 proposer recovering mid-round and the round-1
    proposer taking over could both collect a quorum and fork the chain.
    """
    consensus = _make_consensus(4)
    height = 9
    round0 = consensus.select_proposer(height, 0)
    round1 = consensus.select_proposer(height, 1)
    local = next(a for a in consensus.validators if a not in {round0, round1})

    pbft = PBFTConsensus(consensus, private_key="", chain_id="test", local_validator=local)

    def _pp(sender: str, view: int, block_hash: str) -> PBFTMessage:
        return PBFTMessage(
            message_type=PBFTMessageType.PRE_PREPARE,
            sender=sender,
            view_number=view,
            sequence_number=height,
            digest=pbft.get_message_digest(block_hash, height, view),
            signature="",
            timestamp=0.0,
            block_hash=block_hash,
        )

    first = _pp(round0, 0, "0x" + "aa" * 32)
    second = _pp(round1, 1, "0x" + "bb" * 32)
    pbft.state.pre_prepare_messages[f"{height}:0"] = first
    pbft.state.pre_prepare_messages[f"{height}:1"] = second

    await pbft.prepare_phase(local, first)
    assert pbft._prepared_heights[height] == first.block_hash
    assert f"{height}:0" in pbft.state.prepared_messages

    assert await pbft.prepare_phase(local, second) is False
    assert f"{height}:1" not in pbft.state.prepared_messages
