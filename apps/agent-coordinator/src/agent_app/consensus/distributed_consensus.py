"""
Distributed Consensus Implementation for AITBC Agent Coordinator
Implements various consensus algorithms for distributed decision making
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from aitbc.aitbc_logging import get_logger

from ..storage.consensus_store import ConsensusStore as _ConsensusStore

if TYPE_CHECKING:
    from ..storage.consensus_store import ConsensusStore

logger = get_logger(__name__)

# Expected failure surface for the best-effort consensus handlers below:
# in-memory data-shape and arithmetic/decode errors only. Persistence write
# failures are caught separately via _PERSIST_ERRORS so a DB outage degrades
# to in-memory operation instead of breaking the API (#2164).
_OPS_ERRORS = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    IndexError,
    ArithmeticError,
    RuntimeError,
)

# Persistence adds filesystem/OS and SQLAlchemy transport errors on top of
# the in-memory surface (JSON decode errors are already ValueError).
_PERSIST_ERRORS: tuple[type[Exception], ...]
try:
    from sqlalchemy.exc import SQLAlchemyError

    _PERSIST_ERRORS = _OPS_ERRORS + (OSError, SQLAlchemyError)
except ImportError:
    _PERSIST_ERRORS = _OPS_ERRORS + (OSError,)

_VALID_ALGORITHMS = ("majority_vote", "supermajority", "unanimous")


@dataclass
class ConsensusProposal:
    """Represents a consensus proposal"""

    proposal_id: str
    proposer_id: str
    proposal_data: dict[str, Any]
    timestamp: datetime
    deadline: datetime
    required_votes: int
    current_votes: dict[str, bool] = field(default_factory=dict)
    status: str = "pending"


@dataclass
class ConsensusNode:
    """Represents a node in the consensus network"""

    node_id: str
    endpoint: str
    last_seen: datetime
    reputation_score: float = 1.0
    voting_power: float = 1.0
    is_active: bool = True


class DistributedConsensus:
    """Distributed consensus implementation with multiple algorithms"""

    def __init__(self, store: ConsensusStore | None = None) -> None:
        self.nodes: dict[str, ConsensusNode] = {}
        self.proposals: dict[str, ConsensusProposal] = {}
        self.consensus_history: list[dict[str, Any]] = []
        self.current_algorithm = "majority_vote"
        self.voting_timeout = timedelta(minutes=5)
        self.min_participation = 0.5
        # Write-through persistence (#2164): ``store=None`` keeps the pure
        # in-memory path for tests; the module singleton gets a real store.
        self._store = store
        if store is not None:
            self._hydrate()

    def _hydrate(self) -> None:
        """Load persisted consensus state into the in-memory dicts.

        Best-effort: if the store cannot be read (DB down, unwritable path),
        the store is dropped so this process cannot overwrite good persisted
        rows with state derived from an empty cache.
        """
        store = self._store
        if store is None:
            return
        try:
            state = store.load_all()
        except _PERSIST_ERRORS as e:
            logger.error("Consensus persistence hydration failed; running without durable store: %s", e)
            self._store = None
            return
        for raw in state["nodes"]:
            self.nodes[raw["node_id"]] = ConsensusNode(
                node_id=raw["node_id"],
                endpoint=raw["endpoint"],
                last_seen=datetime.fromtimestamp(raw["last_seen"], UTC),
                reputation_score=raw["reputation_score"],
                voting_power=raw["voting_power"],
                is_active=raw["is_active"],
            )
        for raw in state["proposals"]:
            self.proposals[raw["proposal_id"]] = ConsensusProposal(
                proposal_id=raw["proposal_id"],
                proposer_id=raw["proposer_id"],
                proposal_data=raw["proposal_data"],
                timestamp=datetime.fromtimestamp(raw["timestamp"], UTC),
                deadline=datetime.fromtimestamp(raw["deadline"], UTC),
                required_votes=raw["required_votes"],
                current_votes=dict(raw["current_votes"]),
                status=raw["status"],
            )
        self.consensus_history = [dict(record) for record in state["history"]]
        algorithm = state.get("algorithm")
        if algorithm in _VALID_ALGORITHMS:
            self.current_algorithm = algorithm

    def _persist(self, what: str, write: Callable[[], None]) -> None:
        """Run one store write, logging failures without breaking the API."""
        try:
            write()
        except _PERSIST_ERRORS as e:
            logger.error("Consensus persistence write failed (%s): %s", what, e)

    def _save_node(self, node: ConsensusNode) -> None:
        store = self._store
        if store is not None:
            self._persist("node", lambda: store.upsert_node(node))

    def _save_proposal(self, proposal: ConsensusProposal) -> None:
        store = self._store
        if store is not None:
            self._persist("proposal", lambda: store.upsert_proposal(proposal))

    def _delete_proposal(self, proposal_id: str) -> None:
        store = self._store
        if store is not None:
            self._persist("proposal_delete", lambda: store.delete_proposal(proposal_id))

    def _save_history(self, record: dict[str, Any]) -> None:
        store = self._store
        if store is not None:
            self._persist("history", lambda: store.append_history(record))

    def _save_algorithm(self, algorithm: str) -> None:
        store = self._store
        if store is not None:
            self._persist("algorithm", lambda: store.set_algorithm(algorithm))

    def register_node(self, node_data: dict[str, Any]) -> dict[str, Any]:
        """Register a new node in the consensus network"""
        try:
            node_id = node_data.get("node_id", str(uuid.uuid4()))
            endpoint = node_data.get("endpoint", "")
            node = ConsensusNode(
                node_id=node_id,
                endpoint=endpoint,
                last_seen=datetime.now(UTC),
                reputation_score=node_data.get("reputation_score", 1.0),
                voting_power=node_data.get("voting_power", 1.0),
                is_active=True,
            )
            self.nodes[node_id] = node
            self._save_node(node)
            return {
                "status": "success",
                "node_id": node_id,
                "registered_at": datetime.now(UTC).isoformat(),
                "total_nodes": len(self.nodes),
            }
        except _OPS_ERRORS as e:
            logger.error("Error registering node: %s", e)
            return {"status": "error", "message": str(e)}

    def create_proposal(self, proposal_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new consensus proposal"""
        try:
            proposal_id = str(uuid.uuid4())
            proposer_id = proposal_data.get("proposer_id", "")
            if self.current_algorithm == "majority_vote":
                required_votes = max(1, len(self.nodes) // 2 + 1)
            elif self.current_algorithm == "supermajority":
                required_votes = max(1, int(len(self.nodes) * 0.67))
            elif self.current_algorithm == "unanimous":
                required_votes = len(self.nodes)
            else:
                required_votes = max(1, len(self.nodes) // 2 + 1)
            proposal = ConsensusProposal(
                proposal_id=proposal_id,
                proposer_id=proposer_id,
                proposal_data=proposal_data.get("content", {}),
                timestamp=datetime.now(UTC),
                deadline=datetime.now(UTC) + self.voting_timeout,
                required_votes=required_votes,
            )
            self.proposals[proposal_id] = proposal
            # Persist before _initiate_voting: if voting finalizes the proposal
            # immediately, _cleanup_old_proposals deletes the row again.
            self._save_proposal(proposal)
            self._initiate_voting(proposal)
            return {
                "status": "success",
                "proposal_id": proposal_id,
                "required_votes": required_votes,
                "deadline": proposal.deadline.isoformat(),
                "algorithm": self.current_algorithm,
            }
        except _OPS_ERRORS as e:
            logger.error("Error creating proposal: %s", e)
            return {"status": "error", "message": str(e)}

    def _initiate_voting(self, proposal: ConsensusProposal) -> None:
        """Initiate voting for a proposal.

        ponytail: Previously this simulated random votes at creation, making
        real ``cast_vote`` calls irrelevant. Votes are now only accepted through
        the public ``cast_vote`` API.
        """
        try:
            self._check_consensus(proposal)
        except _OPS_ERRORS as e:
            logger.error("Error initiating voting: %s", e)

    def cast_vote(self, proposal_id: str, node_id: str, vote: bool) -> dict[str, Any]:
        """Cast a vote for a proposal"""
        try:
            if proposal_id not in self.proposals:
                return {"status": "error", "message": "Proposal not found"}
            proposal = self.proposals[proposal_id]
            if proposal.status != "pending":
                return {"status": "error", "message": f"Proposal is {proposal.status}"}
            if node_id not in self.nodes:
                return {"status": "error", "message": "Node not registered"}
            proposal.current_votes[node_id] = vote
            self.nodes[node_id].last_seen = datetime.now(UTC)
            self._save_proposal(proposal)
            self._save_node(self.nodes[node_id])
            self._check_consensus(proposal)
            return {
                "status": "success",
                "proposal_id": proposal_id,
                "node_id": node_id,
                "vote": vote,
                "votes_count": len(proposal.current_votes),
                "required_votes": proposal.required_votes,
            }
        except _OPS_ERRORS as e:
            logger.error("Error casting vote: %s", e)
            return {"status": "error", "message": str(e)}

    def _consensus_outcome(
        self, proposal: ConsensusProposal, yes_votes: int, no_votes: int, total_votes: int
    ) -> tuple[bool, str] | None:
        """Apply the configured voting rule; None while the outcome is undecided."""
        required = proposal.required_votes
        if self.current_algorithm == "majority_vote":
            if yes_votes >= required:
                return True, f"Majority reached: {yes_votes}/{total_votes}"
            if no_votes >= required:
                return False, f"Majority against: {no_votes}/{total_votes}"
        elif self.current_algorithm == "supermajority":
            if yes_votes >= required:
                return True, f"Supermajority reached: {yes_votes}/{total_votes}"
            if no_votes >= required:
                return False, f"Supermajority against: {no_votes}/{total_votes}"
        elif self.current_algorithm == "unanimous":
            if total_votes == len(self.nodes) and yes_votes == total_votes:
                return True, "Unanimous approval"
            if no_votes > 0:
                return False, f"Not unanimous: {yes_votes}/{total_votes}"
        return None

    def _check_consensus(self, proposal: ConsensusProposal) -> None:
        """Check if consensus is reached for a proposal"""
        try:
            if proposal.status != "pending":
                return
            yes_votes = sum(1 for vote in proposal.current_votes.values() if vote)
            no_votes = len(proposal.current_votes) - yes_votes
            total_votes = len(proposal.current_votes)
            if datetime.now(UTC) > proposal.deadline:
                proposal.status = "expired"
                self._finalize_proposal(proposal, False, "Deadline expired")
                return
            active_nodes = sum(1 for node in self.nodes.values() if node.is_active)
            if total_votes < active_nodes * self.min_participation:
                return
            outcome = self._consensus_outcome(proposal, yes_votes, no_votes, total_votes)
            if outcome is None:
                return
            approved, reason = outcome
            proposal.status = "approved" if approved else "rejected"
            self._finalize_proposal(proposal, approved, reason)
        except _OPS_ERRORS as e:
            logger.error("Error checking consensus: %s", e)

    def _finalize_proposal(self, proposal: ConsensusProposal, approved: bool, reason: str) -> None:
        """Finalize a proposal decision"""
        try:
            history_record = {
                "proposal_id": proposal.proposal_id,
                "proposer_id": proposal.proposer_id,
                "proposal_data": proposal.proposal_data,
                "approved": approved,
                "reason": reason,
                "votes": dict(proposal.current_votes),
                "required_votes": proposal.required_votes,
                "finalized_at": datetime.now(UTC).isoformat(),
                "algorithm": self.current_algorithm,
            }
            self.consensus_history.append(history_record)
            self._save_history(history_record)
            self._cleanup_old_proposals()
            logger.info("Proposal %s %s: %s", proposal.proposal_id, "approved" if approved else "rejected", reason)
        except _OPS_ERRORS as e:
            logger.error("Error finalizing proposal: %s", e)

    def _cleanup_old_proposals(self) -> None:
        """Clean up old and expired proposals"""
        try:
            current_time = datetime.now(UTC)
            expired_proposals = [
                pid
                for pid, proposal in self.proposals.items()
                if proposal.deadline < current_time or proposal.status in ["approved", "rejected", "expired"]
            ]
            for pid in expired_proposals:
                del self.proposals[pid]
                self._delete_proposal(pid)
        except _OPS_ERRORS as e:
            logger.error("Error cleaning up proposals: %s", e)

    def get_proposal_status(self, proposal_id: str) -> dict[str, Any]:
        """Get the status of a proposal"""
        try:
            if proposal_id not in self.proposals:
                return {"status": "error", "message": "Proposal not found"}
            proposal = self.proposals[proposal_id]
            yes_votes = sum(1 for vote in proposal.current_votes.values() if vote)
            no_votes = len(proposal.current_votes) - yes_votes
            return {
                "status": proposal.status,
                "proposal_id": proposal_id,
                "proposer_id": proposal.proposer_id,
                "created_at": proposal.timestamp.isoformat(),
                "deadline": proposal.deadline.isoformat(),
                "required_votes": proposal.required_votes,
                "current_votes": {
                    "yes": yes_votes,
                    "no": no_votes,
                    "total": len(proposal.current_votes),
                    "details": proposal.current_votes,
                },
                "algorithm": self.current_algorithm,
            }
        except _OPS_ERRORS as e:
            logger.error("Error getting proposal status: %s", e)
            return {"status": "error", "message": str(e)}

    def set_consensus_algorithm(self, algorithm: str) -> dict[str, Any]:
        """Set the consensus algorithm"""
        try:
            if algorithm not in _VALID_ALGORITHMS:
                return {"status": "error", "message": f"Invalid algorithm. Valid options: {list(_VALID_ALGORITHMS)}"}
            self.current_algorithm = algorithm
            self._save_algorithm(algorithm)
            return {"status": "success", "algorithm": algorithm, "changed_at": datetime.now(UTC).isoformat()}
        except _OPS_ERRORS as e:
            logger.error("Error setting consensus algorithm: %s", e)
            return {"status": "error", "message": str(e)}

    def get_consensus_statistics(self) -> dict[str, Any]:
        """Get comprehensive consensus statistics"""
        try:
            total_proposals = len(self.consensus_history)
            active_nodes = sum(1 for node in self.nodes.values() if node.is_active)
            if total_proposals == 0:
                return {
                    "status": "success",
                    "total_proposals": 0,
                    "active_nodes": active_nodes,
                    "current_algorithm": self.current_algorithm,
                    "message": "No proposals processed yet",
                }
            approved_proposals = sum(1 for record in self.consensus_history if record["approved"])
            rejected_proposals = total_proposals - approved_proposals
            algorithm_stats: defaultdict[str, dict[str, Any]] = defaultdict(lambda: {"approved": 0, "total": 0})
            for record in self.consensus_history:
                algorithm = record["algorithm"]
                algorithm_stats[algorithm]["total"] += 1
                if record["approved"]:
                    algorithm_stats[algorithm]["approved"] += 1
            for _algorithm, stats in algorithm_stats.items():
                stats["success_rate"] = stats["approved"] / stats["total"] if stats["total"] > 0 else 0
            node_participation = {}
            for node_id, node in self.nodes.items():
                votes_cast = sum(1 for record in self.consensus_history if node_id in record["votes"])
                node_participation[node_id] = {
                    "votes_cast": votes_cast,
                    "participation_rate": votes_cast / total_proposals if total_proposals > 0 else 0,
                    "reputation_score": node.reputation_score,
                }
            return {
                "status": "success",
                "total_proposals": total_proposals,
                "approved_proposals": approved_proposals,
                "rejected_proposals": rejected_proposals,
                "success_rate": approved_proposals / total_proposals,
                "active_nodes": active_nodes,
                "total_nodes": len(self.nodes),
                "current_algorithm": self.current_algorithm,
                "algorithm_performance": dict(algorithm_stats),
                "node_participation": node_participation,
                "active_proposals": len(self.proposals),
                "last_updated": datetime.now(UTC).isoformat(),
            }
        except _OPS_ERRORS as e:
            logger.error("Error getting consensus statistics: %s", e)
            return {"status": "error", "message": str(e)}

    def update_node_status(self, node_id: str, is_active: bool) -> dict[str, Any]:
        """Update a node's active status"""
        try:
            if node_id not in self.nodes:
                return {"status": "error", "message": "Node not found"}
            self.nodes[node_id].is_active = is_active
            self.nodes[node_id].last_seen = datetime.now(UTC)
            self._save_node(self.nodes[node_id])
            return {
                "status": "success",
                "node_id": node_id,
                "is_active": is_active,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        except _OPS_ERRORS as e:
            logger.error("Error updating node status: %s", e)
            return {"status": "error", "message": str(e)}


distributed_consensus = DistributedConsensus(store=_ConsensusStore())
