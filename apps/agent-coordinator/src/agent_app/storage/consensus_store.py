"""Durable store for agent-coordinator distributed-consensus state.

Persists ``DistributedConsensus`` nodes, open proposals (with cast votes),
finalized-proposal history, and the selected algorithm to the shared agent
SQLite database (``aitbc.db`` — same machinery ``TaskEscrowStore`` and the
coin-request ledger use) so consensus state survives coordinator restarts
(#2164).

``DistributedConsensus`` keeps the rows hot in memory as a write-through
cache and reloads them via :meth:`ConsensusStore.load_all` at startup.
Table creation is deferred to the first call (:meth:`_ensure`) so importing
the module — which happens at app import time via the consensus router —
never touches the database.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from aitbc.aitbc_logging import get_logger
from aitbc.db import get_db_session, init_db
from aitbc.models import (
    ConsensusHistoryRecord,
    ConsensusMetaRecord,
    ConsensusNodeRecord,
    ConsensusProposalRecord,
)

if TYPE_CHECKING:
    from ..consensus.distributed_consensus import ConsensusNode, ConsensusProposal

logger = get_logger(__name__)

_ALGORITHM_KEY = "current_algorithm"


class ConsensusStore:
    """SQLite-backed persistence for ``DistributedConsensus`` state."""

    def __init__(self) -> None:
        # init_db/create_all is deferred to first use — see module docstring.
        self._ensured = False

    def _ensure(self) -> None:
        """Create the shared tables once, lazily, on first DB access."""
        if not self._ensured:
            init_db()
            self._ensured = True

    def load_all(self) -> dict[str, Any]:
        """Return persisted consensus state as plain dicts for hydration.

        Shape::

            {
                "nodes":     [{node_id, endpoint, last_seen, reputation_score,
                               voting_power, is_active}],
                "proposals": [{proposal_id, proposer_id, proposal_data,
                               timestamp, deadline, required_votes,
                               current_votes, status}],
                "history":   [<consensus_history record dicts, append order>],
                "algorithm": <current_algorithm string or None>,
            }

        ``last_seen``/``timestamp``/``deadline`` are Unix epoch floats;
        ``proposal_data``/``current_votes``/history ``record`` are decoded
        JSON. Only *open* proposals are stored — finalized proposals are
        deleted on cleanup and live on as history rows.
        """
        self._ensure()
        with get_db_session() as session:
            nodes = [
                {
                    "node_id": node_row.node_id,
                    "endpoint": node_row.endpoint,
                    "last_seen": node_row.last_seen,
                    "reputation_score": node_row.reputation_score,
                    "voting_power": node_row.voting_power,
                    "is_active": node_row.is_active,
                }
                for node_row in session.query(ConsensusNodeRecord).all()
            ]
            proposals = []
            for proposal_row in session.query(ConsensusProposalRecord).all():
                try:
                    proposal_data = json.loads(proposal_row.proposal_data or "{}")
                except (TypeError, ValueError):
                    logger.warning("Unreadable proposal_data on %s", proposal_row.proposal_id)
                    proposal_data = {}
                try:
                    current_votes = json.loads(proposal_row.current_votes or "{}")
                except (TypeError, ValueError):
                    logger.warning("Unreadable current_votes on %s", proposal_row.proposal_id)
                    current_votes = {}
                proposals.append(
                    {
                        "proposal_id": proposal_row.proposal_id,
                        "proposer_id": proposal_row.proposer_id,
                        "proposal_data": proposal_data,
                        "timestamp": proposal_row.timestamp,
                        "deadline": proposal_row.deadline,
                        "required_votes": proposal_row.required_votes,
                        "current_votes": current_votes,
                        "status": proposal_row.status,
                    }
                )
            history = []
            history_rows = session.query(ConsensusHistoryRecord).order_by(ConsensusHistoryRecord.id).all()
            for history_row in history_rows:
                try:
                    history.append(json.loads(history_row.record))
                except (TypeError, ValueError):
                    logger.warning("Unreadable consensus history record %s", history_row.id)
            algorithm_row = session.get(ConsensusMetaRecord, _ALGORITHM_KEY)
        return {
            "nodes": nodes,
            "proposals": proposals,
            "history": history,
            "algorithm": algorithm_row.value if algorithm_row is not None else None,
        }

    def upsert_node(self, node: ConsensusNode) -> None:
        """Insert or update the durable row for ``node``."""
        self._ensure()
        with get_db_session() as session:
            row = session.get(ConsensusNodeRecord, node.node_id)
            if row is None:
                row = ConsensusNodeRecord()
                row.node_id = node.node_id
                session.add(row)
            row.endpoint = node.endpoint
            row.last_seen = node.last_seen.timestamp()
            row.reputation_score = node.reputation_score
            row.voting_power = node.voting_power
            row.is_active = node.is_active

    def upsert_proposal(self, proposal: ConsensusProposal) -> None:
        """Insert or update the durable row for ``proposal`` (votes included)."""
        self._ensure()
        with get_db_session() as session:
            row = session.get(ConsensusProposalRecord, proposal.proposal_id)
            if row is None:
                row = ConsensusProposalRecord()
                row.proposal_id = proposal.proposal_id
                session.add(row)
            row.proposer_id = proposal.proposer_id
            row.proposal_data = json.dumps(proposal.proposal_data)
            row.timestamp = proposal.timestamp.timestamp()
            row.deadline = proposal.deadline.timestamp()
            row.required_votes = proposal.required_votes
            row.current_votes = json.dumps(proposal.current_votes)
            row.status = proposal.status

    def delete_proposal(self, proposal_id: str) -> None:
        """Remove the durable row for a finalized/cleaned-up proposal."""
        self._ensure()
        with get_db_session() as session:
            row = session.get(ConsensusProposalRecord, proposal_id)
            if row is not None:
                session.delete(row)

    def append_history(self, record: dict[str, Any]) -> None:
        """Append a finalized-proposal record to ``consensus_history``."""
        self._ensure()
        with get_db_session() as session:
            history_row = ConsensusHistoryRecord()
            history_row.proposal_id = str(record.get("proposal_id", ""))
            history_row.record = json.dumps(record)
            session.add(history_row)

    def set_algorithm(self, algorithm: str) -> None:
        """Persist the selected consensus algorithm."""
        self._ensure()
        with get_db_session() as session:
            row = session.get(ConsensusMetaRecord, _ALGORITHM_KEY)
            if row is None:
                row = ConsensusMetaRecord()
                row.key = _ALGORITHM_KEY
                session.add(row)
            row.value = algorithm
