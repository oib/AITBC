"""#1940 F3-B — dormant cross-view PBFT commit lock.

Once ``pbft_cross_view_commit_lock_height`` is armed, a validator may not
emit two different COMMIT hashes for the same sequence (chain height) across
PBFT views: the first committed ``block_hash`` per sequence is locked —
persisted on ``ConsensusState.pbft_commit_locks_json`` BEFORE the commit is
broadcast — and a later-view commit for a different hash is refused (log +
metric, nothing stored or gossiped). Same-hash commits in later views stay
legal, prepare-phase rotation is untouched (a failed round must still be
superseded for liveness), incoming conflicting commits remain F3-A
evidence, and a commit quorum for an unlocked hash cannot trigger local
execution.

Everything is dormant: with the gate unset the engine is byte-identical to
the pre-F3-B rotation behavior, which the unarmed control test pins. These
tests arm the gate via ``settings`` monkeypatch only — the production
height is NOT armed (the committed-but-unsealed liveness decision is #2005).
"""

from __future__ import annotations

import pytest

from aitbc_chain.config import settings
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.pbft import (
    PBFTConsensus,
    PBFTMessage,
    PBFTMessageType,
)

HEIGHT = 10
HASH_A = "0x" + "aa" * 32
HASH_B = "0x" + "bb" * 32
HASH_C = "0x" + "cc" * 32


def _chain_db(chain_id: str):
    """Materialize a test chain.db so ``save_state``/``load_state`` hit a real
    sqlite file (same helper shape as test_validator_deactivation_1198)."""
    from pathlib import Path

    from aitbc_chain.database import get_engine
    from aitbc_chain.metadata import chain_metadata

    Path(settings.get_db_path(chain_id)).parent.mkdir(parents=True, exist_ok=True)
    engine = get_engine(chain_id, create_ok=True)
    chain_metadata.create_all(engine)
    return engine


def _make_consensus(n_validators: int = 4, chain_id: str = "test-pbft-lock") -> MultiValidatorPoA:
    _chain_db(chain_id)
    consensus = MultiValidatorPoA(chain_id)
    for i in range(n_validators):
        addr = f"0x{i:040x}"
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return consensus


def _pbft(consensus: MultiValidatorPoA, local: str, chain_id: str = "test") -> PBFTConsensus:
    return PBFTConsensus(consensus, private_key="", chain_id=chain_id, local_validator=local)


def _prepare_msg(pbft: PBFTConsensus, sender: str, block_hash: str, view: int, seq: int) -> PBFTMessage:
    """A prepare-phase message as a peer would send it (unsigned — conftest
    disables ``pbft_require_signatures`` for this suite)."""
    return PBFTMessage(
        message_type=PBFTMessageType.PREPARE,
        sender=sender,
        view_number=view,
        sequence_number=seq,
        digest=pbft.get_message_digest(block_hash, seq, view),
        signature="",
        timestamp=0.0,
        block_hash=block_hash,
    )


def _pre_prepare_msg(pbft: PBFTConsensus, sender: str, block_hash: str, view: int, seq: int) -> PBFTMessage:
    return PBFTMessage(
        message_type=PBFTMessageType.PRE_PREPARE,
        sender=sender,
        view_number=view,
        sequence_number=seq,
        digest=pbft.get_message_digest(block_hash, seq, view),
        signature="",
        timestamp=0.0,
        block_hash=block_hash,
    )


def _commit_msg(pbft: PBFTConsensus, sender: str, block_hash: str, view: int, seq: int) -> PBFTMessage:
    return PBFTMessage(
        message_type=PBFTMessageType.COMMIT,
        sender=sender,
        view_number=view,
        sequence_number=seq,
        digest=pbft.get_message_digest(block_hash, seq, view),
        signature="",
        timestamp=0.0,
        block_hash=block_hash,
    )


def _seed_commit_quorum(pbft: PBFTConsensus, block_hash: str, view: int, seq: int, senders: list[str]) -> None:
    """Fill ``committed_messages[f"{seq}:{view}"]`` with one commit per sender."""
    pbft.state.committed_messages[f"{seq}:{view}"] = [_commit_msg(pbft, s, block_hash, view, seq) for s in senders]


@pytest.fixture
def _lock_armed(monkeypatch):
    monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", 0)


class TestCommitLockUnit:
    @pytest.mark.asyncio
    async def test_armed_lock_refuses_conflicting_later_view_commit(self, _lock_armed):
        """Commit HASH_A at view 0, then HASH_B at view 1: refused — nothing
        stored, nothing broadcast, lock unchanged."""
        consensus = _make_consensus(4, "pbft-lock-u1")
        local = list(consensus.validators)[0]
        pbft = _pbft(consensus, local)
        peer = list(consensus.validators)[1]

        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 0, HEIGHT))
        assert len(pbft.state.committed_messages[f"{HEIGHT}:0"]) == 1
        assert consensus.pbft_commit_lock_get(HEIGHT) == HASH_A
        assert pbft._commit_locks[HEIGHT] == HASH_A

        result = await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_B, 1, HEIGHT))

        assert result is False
        assert not pbft.state.committed_messages.get(f"{HEIGHT}:1")
        assert f"{HEIGHT}:1" not in pbft._local_committed
        assert consensus.pbft_commit_lock_get(HEIGHT) == HASH_A
        assert pbft._commit_locks[HEIGHT] == HASH_A

    @pytest.mark.asyncio
    async def test_armed_lock_allows_same_hash_later_view_commit(self, _lock_armed):
        """Same block_hash in a later view cannot fork the value — allowed."""
        consensus = _make_consensus(4, "pbft-lock-u2")
        local = list(consensus.validators)[0]
        pbft = _pbft(consensus, local)
        peer = list(consensus.validators)[1]

        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 0, HEIGHT))
        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 1, HEIGHT))

        assert len(pbft.state.committed_messages[f"{HEIGHT}:1"]) == 1
        assert pbft.state.committed_messages[f"{HEIGHT}:1"][0].block_hash == HASH_A
        assert consensus.pbft_commit_lock_get(HEIGHT) == HASH_A

    @pytest.mark.asyncio
    async def test_armed_lock_preserves_prepare_rotation(self, _lock_armed):
        """The lock gates COMMIT votes only: preparing a different hash in a
        later view — the liveness mechanism for a dead proposer — still works
        after a commit lock exists."""
        consensus = _make_consensus(4, "pbft-lock-u3")
        local = list(consensus.validators)[0]
        pbft = _pbft(consensus, local)
        peer = list(consensus.validators)[1]

        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 0, HEIGHT))
        assert consensus.pbft_commit_lock_get(HEIGHT) == HASH_A

        pp_b = _pre_prepare_msg(pbft, peer, HASH_B, 1, HEIGHT)
        pbft.state.pre_prepare_messages[f"{HEIGHT}:1"] = pp_b
        await pbft.prepare_phase(local, pp_b)

        assert f"{HEIGHT}:1" in pbft.state.prepared_messages
        assert pbft._prepared_heights[HEIGHT] == (1, HASH_B)
        # ...but committing that prepared hash is still refused.
        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_B, 1, HEIGHT))
        assert not pbft.state.committed_messages.get(f"{HEIGHT}:1")

    @pytest.mark.asyncio
    async def test_unarmed_gate_keeps_legacy_rotation(self):
        """Control: with the gate unset a different-hash later-view commit is
        still emitted — the pre-F3-B behavior is byte-identical."""
        consensus = _make_consensus(4, "pbft-lock-u4")
        local = list(consensus.validators)[0]
        pbft = _pbft(consensus, local)
        peer = list(consensus.validators)[1]

        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 0, HEIGHT))
        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_B, 1, HEIGHT))

        assert len(pbft.state.committed_messages[f"{HEIGHT}:1"]) == 1
        assert pbft.state.committed_messages[f"{HEIGHT}:1"][0].block_hash == HASH_B
        assert consensus.pbft_commit_lock_get(HEIGHT) is None
        assert pbft._commit_locks == {}

    @pytest.mark.asyncio
    async def test_lock_arm_persistence_failure_fails_closed(self, _lock_armed, monkeypatch):
        """#1268 precedent: if the lock cannot be persisted the commit must
        NOT be broadcast — arming happens before emission, never after."""
        consensus = _make_consensus(4, "pbft-lock-u5")
        local = list(consensus.validators)[0]
        pbft = _pbft(consensus, local)
        peer = list(consensus.validators)[1]
        monkeypatch.setattr(consensus, "_pbft_safety_persist", lambda: False)  # #2190

        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 0, HEIGHT))

        assert not pbft.state.committed_messages.get(f"{HEIGHT}:0")
        assert f"{HEIGHT}:0" not in pbft._local_committed
        assert consensus.pbft_commit_lock_get(HEIGHT) is None
        assert pbft._commit_locks == {}

    @pytest.mark.asyncio
    async def test_incoming_conflicting_commit_untouched(self, _lock_armed):
        """The lock gates only LOCALLY emitted commits: an incoming commit
        for a different hash still lands in the bucket — it is F3-A slashing
        evidence, not a local vote."""
        consensus = _make_consensus(4, "pbft-lock-u6")
        local = list(consensus.validators)[0]
        pbft = _pbft(consensus, local)
        peer = list(consensus.validators)[1]

        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 0, HEIGHT))
        incoming = _commit_msg(pbft, peer, HASH_B, 1, HEIGHT)
        await pbft.handle_incoming_message(incoming.to_dict())

        assert len(pbft.state.committed_messages[f"{HEIGHT}:1"]) == 1
        assert pbft.state.committed_messages[f"{HEIGHT}:1"][0].block_hash == HASH_B
        assert consensus.pbft_commit_lock_get(HEIGHT) == HASH_A


class TestCommitLockPersistence:
    @pytest.mark.asyncio
    async def test_lock_survives_save_state_load_state(self, _lock_armed):
        """Arm a lock, rebuild MultiValidatorPoA from the same chain_id —
        the persisted ConsensusState row must restore it, and a fresh
        PBFTConsensus must still refuse the conflicting later-view commit."""
        chain = "pbft-lock-restart"
        consensus = _make_consensus(4, chain)
        local = list(consensus.validators)[0]
        peer = list(consensus.validators)[1]
        pbft = _pbft(consensus, local)

        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 0, HEIGHT))
        assert consensus.pbft_commit_lock_get(HEIGHT) == HASH_A

        reloaded = MultiValidatorPoA(chain)
        assert reloaded.pbft_commit_lock_get(HEIGHT) == HASH_A
        assert HEIGHT in reloaded.pbft_commit_locks()

        pbft2 = _pbft(reloaded, local)
        assert pbft2._commit_locks.get(HEIGHT) == HASH_A
        await pbft2.commit_phase(local, _prepare_msg(pbft2, peer, HASH_B, 1, HEIGHT))
        assert not pbft2.state.committed_messages.get(f"{HEIGHT}:1")
        # Same-hash later-view commit still allowed after restart.
        await pbft2.commit_phase(local, _prepare_msg(pbft2, peer, HASH_A, 1, HEIGHT))
        assert len(pbft2.state.committed_messages[f"{HEIGHT}:1"]) == 1

    @pytest.mark.asyncio
    async def test_persisted_row_shape_is_canonical(self, _lock_armed):
        """The JSON column round-trips as {str(seq): hash} with ascending
        int-key order — deterministic bytes for replay/audit."""
        import json

        chain = "pbft-lock-shape"
        consensus = _make_consensus(4, chain)
        assert consensus.save_state() is True
        # Arm the higher sequence FIRST: arming prunes locks below the armed
        # height, so the lower one must come second to coexist in the row.
        consensus.pbft_commit_lock_arm(HEIGHT + 2, HASH_B)
        consensus.pbft_commit_lock_arm(HEIGHT, HASH_A)

        # #2190: the arm persists to the safety store file, not the DB column.
        stored = consensus._pbft_safety_store.load()
        assert stored is not None
        raw = stored["commit_locks"]
        data = json.loads(raw)
        assert data == {str(HEIGHT): HASH_A, str(HEIGHT + 2): HASH_B}
        assert list(data.keys()) == [str(HEIGHT), str(HEIGHT + 2)]


class TestExecutePhaseGuard:
    @pytest.mark.asyncio
    async def test_different_hash_quorum_cannot_execute(self, _lock_armed):
        """A commit quorum for a hash this node did NOT lock must not trigger
        local execution — the safe-stall half of the safety floor."""
        consensus = _make_consensus(4, "pbft-lock-e1")
        local = list(consensus.validators)[0]
        validators = list(consensus.validators)
        pbft = _pbft(consensus, local)
        peer = validators[1]

        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 0, HEIGHT))
        assert consensus.pbft_commit_lock_get(HEIGHT) == HASH_A

        # Quorum for HASH_B at a later view: seed pre-prepare + 3 commits.
        pp_b = _pre_prepare_msg(pbft, validators[2], HASH_B, 1, HEIGHT)
        pbft.state.pre_prepare_messages[f"{HEIGHT}:1"] = pp_b
        _seed_commit_quorum(pbft, HASH_B, 1, HEIGHT, validators[1:4])

        executed: list[str] = []

        async def _on_execute(block_hash: str, commits: list) -> None:
            executed.append(block_hash)

        pbft.set_on_execute(_on_execute)
        result = await pbft.execute_phase(f"{HEIGHT}:1")

        assert result is False
        assert pbft.state.current_sequence == 0
        assert executed == []

    @pytest.mark.asyncio
    async def test_same_hash_quorum_executes(self, _lock_armed):
        """Positive control: a quorum for the LOCKED hash executes normally."""
        consensus = _make_consensus(4, "pbft-lock-e2")
        local = list(consensus.validators)[0]
        validators = list(consensus.validators)
        pbft = _pbft(consensus, local)
        peer = validators[1]

        await pbft.commit_phase(local, _prepare_msg(pbft, peer, HASH_A, 0, HEIGHT))

        pp_a = _pre_prepare_msg(pbft, validators[2], HASH_A, 1, HEIGHT)
        pbft.state.pre_prepare_messages[f"{HEIGHT}:1"] = pp_a
        _seed_commit_quorum(pbft, HASH_A, 1, HEIGHT, validators[1:4])

        executed: list[str] = []

        async def _on_execute(block_hash: str, commits: list) -> None:
            executed.append(block_hash)

        pbft.set_on_execute(_on_execute)
        result = await pbft.execute_phase(f"{HEIGHT}:1")

        assert result is True
        assert pbft.state.current_sequence == HEIGHT
        assert executed == [HASH_A]

    @pytest.mark.asyncio
    async def test_unlocked_sequence_executes_any_quorum(self, _lock_armed):
        """No lock for the sequence (gate armed but this node never
        committed it) → execution is not restricted by the guard."""
        consensus = _make_consensus(4, "pbft-lock-e3")
        local = list(consensus.validators)[0]
        validators = list(consensus.validators)
        pbft = _pbft(consensus, local)

        pp_b = _pre_prepare_msg(pbft, validators[2], HASH_B, 0, HEIGHT)
        pbft.state.pre_prepare_messages[f"{HEIGHT}:0"] = pp_b
        _seed_commit_quorum(pbft, HASH_B, 0, HEIGHT, validators[1:4])

        result = await pbft.execute_phase(f"{HEIGHT}:0")
        assert result is True
        assert pbft.state.current_sequence == HEIGHT


# ---------------------------------------------------------------------------
# Network tests — the dead-proposer rotation boundary, armed
# ---------------------------------------------------------------------------


def _network_nodes(chain_id: str, n: int):
    """Real-key 4/5-node PBFT network harness (same shape as test_pbft.py)."""
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
    for _ in range(n):
        pk = keys.PrivateKey(secrets.token_bytes(32))
        keypairs.append((pk.public_key.to_checksum_address(), pk.to_hex()))

    _chain_db(chain_id)
    shared_consensus = MultiValidatorPoA(chain_id)
    for addr, _ in keypairs:
        shared_consensus.add_validator(addr, 1000.0)
        shared_consensus.validators[addr].role = ValidatorRole.PROPOSER

    net = Network()
    nodes: dict[str, PBFTConsensus] = {}
    for addr, pk_hex in keypairs:
        node = PBFTConsensus(shared_consensus, private_key=pk_hex, chain_id=chain_id, local_validator=addr)
        node.set_gossip_backend(net)
        net.nodes.append(node)
        nodes[addr] = node
    return net, nodes, shared_consensus


@pytest.mark.asyncio
async def test_armed_prepare_only_round_then_standin_commits(monkeypatch):
    """(a) Armed gate, NO regression: a view that only reaches PREPARE quorum
    (proposer dies before commits can form) must still let the stand-in
    finish the height in the next view — the lock only bites after a commit
    quorum actually happened."""
    from secrets import token_hex

    monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", 0)
    net, nodes, shared_consensus = _network_nodes("test-pbft-lock-prep", 5)
    height = 11  # n=5 -> required = 4

    dead = shared_consensus.select_proposer(height, 0)
    standin = shared_consensus.select_proposer(height, 1)
    assert dead != standin
    extra = next(a for a in nodes if a not in {dead, standin})

    hash_a = "0x" + token_hex(32)
    hash_b = "0x" + token_hex(32)

    # View 0: dead proposes; dead + one more are unreachable -> only 3 live
    # nodes, below the n=5 quorum of 4 -> prepares but NO commits, NO locks.
    net.down.update({dead, extra})
    await nodes[dead].pre_prepare_phase(dead, hash_a, sequence=height, view=0)
    live0 = [a for a in nodes if a not in {dead, extra}]
    assert len(live0) == 3
    for a in live0:
        assert len(nodes[a].state.prepared_messages.get(f"{height}:0", [])) == 3
        assert not nodes[a].state.committed_messages.get(f"{height}:0")
        assert shared_consensus.pbft_commit_lock_get(height) is None

    # View 1: the fourth node returns; the stand-in finishes the height.
    net.down = {dead}
    result = await nodes[standin].propose_and_wait(standin, hash_b, timeout=5.0, sequence=height, view=1)

    assert result is True, "prepare-only view 0 must not block the stand-in's view-1 commit"
    for a in [standin] + [x for x in live0 if x != standin] + [extra]:
        commits = nodes[a].state.committed_messages.get(f"{height}:1", [])
        assert len(commits) == 4
        assert all(m.block_hash == hash_b for m in commits)
    assert shared_consensus.pbft_commit_lock_get(height) == hash_b


@pytest.mark.asyncio
async def test_armed_commit_quorum_then_stall_is_the_safety_boundary(monkeypatch):
    """(b) Armed gate: view 0 reaches a real COMMIT quorum for hash A, the
    proposer dies before sealing, and the view-1 stand-in's different hash B
    can prepare but never commit — the intentional safe stall documented in
    plan §7 (arming is deferred to the #2005 liveness decision)."""
    from secrets import token_hex

    monkeypatch.setattr(settings, "pbft_cross_view_commit_lock_height", 0)
    net, nodes, shared_consensus = _network_nodes("test-pbft-lock-stall", 4)
    height = 7  # n=4 -> required = 3

    dead = shared_consensus.select_proposer(height, 0)
    standin = shared_consensus.select_proposer(height, 1)
    assert dead != standin
    survivors = [a for a in nodes if a != dead]

    hash_a = "0x" + token_hex(32)
    hash_b = "0x" + token_hex(32)

    # View 0: proposer announces; all three survivors prepare AND commit —
    # a full commit quorum forms and each survivor locks hash A at height.
    await nodes[dead].pre_prepare_phase(dead, hash_a, sequence=height, view=0)
    for a in survivors:
        # The dead proposer is still reachable during view 0, so it commits
        # too: each survivor sees all 4 commits for hash A — a full quorum.
        assert len(nodes[a].state.committed_messages.get(f"{height}:0", [])) == 4
        assert nodes[a]._commit_locks.get(height) == hash_a
    assert shared_consensus.pbft_commit_lock_get(height) == hash_a

    # The proposer dies before the block is written.
    net.down.add(dead)

    # View 1: the stand-in's different hash prepares fine (rotation lives),
    # but no survivor may emit a conflicting commit — quorum never forms.
    result = await nodes[standin].propose_and_wait(standin, hash_b, timeout=3.0, sequence=height, view=1)

    assert result is False, "committed-but-unsealed height must stall safely, not fork"
    for a in survivors:
        node = nodes[a]
        # Prepare rotation still worked — the stall is at the commit layer.
        assert len(node.state.prepared_messages.get(f"{height}:1", [])) == 3
        assert not node.state.committed_messages.get(f"{height}:1")
        assert node._commit_locks.get(height) == hash_a
    assert shared_consensus.pbft_commit_lock_get(height) == hash_a
