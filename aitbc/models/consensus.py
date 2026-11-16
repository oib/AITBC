"""Database schema for agent-coordinator distributed-consensus state.

Durable backing for ``agent_app.consensus.distributed_consensus``: node
registrations, open (pending) proposals with their cast votes, finalized
proposal history, and the selected consensus algorithm. The in-memory dicts
in ``DistributedConsensus`` stay the read cache; every mutation is written
through to these tables so a coordinator restart does not wipe consensus
state (#2164).

Timestamps are stored as Unix epoch floats to match ``ConsensusNode`` /
``ConsensusProposal`` exactly — same convention as ``task_escrows``.
``current_votes`` / ``proposal_data`` / ``record`` hold JSON text so the
schema stays free of the consensus module's dataclasses.
"""

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .coin_request import Base


class ConsensusNodeRecord(Base):
    """Persisted consensus-network node registration."""

    __tablename__ = "consensus_nodes"

    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    endpoint: Mapped[str] = mapped_column(String, default="")
    last_seen: Mapped[float] = mapped_column(Float)
    reputation_score: Mapped[float] = mapped_column(Float, default=1.0)
    voting_power: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ConsensusProposalRecord(Base):
    """Persisted open consensus proposal (pending only — finalized rows are deleted)."""

    __tablename__ = "consensus_proposals"

    proposal_id: Mapped[str] = mapped_column(String, primary_key=True)
    proposer_id: Mapped[str] = mapped_column(String, default="")
    proposal_data: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    timestamp: Mapped[float] = mapped_column(Float)
    deadline: Mapped[float] = mapped_column(Float)
    required_votes: Mapped[int] = mapped_column(Integer)
    current_votes: Mapped[str] = mapped_column(Text, default="{}")  # JSON {node_id: bool}
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)


class ConsensusHistoryRecord(Base):
    """Persisted finalized-proposal record (the ``consensus_history`` entries)."""

    __tablename__ = "consensus_history"

    # Autoincrement preserves append order for statistics replay.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(String, index=True)
    record: Mapped[str] = mapped_column(Text)  # JSON


class ConsensusMetaRecord(Base):
    """Key/value persistence for instance-level consensus settings."""

    __tablename__ = "consensus_meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
