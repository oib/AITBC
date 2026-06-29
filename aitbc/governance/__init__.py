"""AITBC on-chain governance shared SDK (v0.7.3).

Provides:
- GovernanceTxType: enum for GOVERNANCE_PROPOSE / VOTE / EXECUTE tx types
- ProposalType / VoteChoice: governance domain enums
- GovernanceConfig: governance client + voting parameter configuration
- ProposalData / VoteData / ExecuteData: on-chain tx payload dataclasses
- ParameterChangeSchema: parameter change proposal schema
- GovernanceClient: async HTTP client for the governance service REST API
- build_proposal_tx / build_vote_tx / build_execute_tx: on-chain tx
  payload builders
- build_parameter_change_params: parameter change parameters builder
- validate_governance_payload: governance tx payload validation (used by
  blockchain-node consensus layer, Agent B B7)
"""

from __future__ import annotations

from .client import GovernanceClient
from .onchain import (
    build_execute_tx,
    build_parameter_change_params,
    build_proposal_tx,
    build_vote_tx,
    validate_governance_payload,
)
from .types import (
    ExecuteData,
    GovernanceConfig,
    GovernanceTxType,
    ParameterChangeSchema,
    ProposalData,
    ProposalType,
    VoteChoice,
    VoteData,
)

__all__ = [
    "ExecuteData",
    "GovernanceClient",
    "GovernanceConfig",
    "GovernanceTxType",
    "ParameterChangeSchema",
    "ProposalData",
    "ProposalType",
    "VoteChoice",
    "VoteData",
    "build_execute_tx",
    "build_parameter_change_params",
    "build_proposal_tx",
    "build_vote_tx",
    "validate_governance_payload",
]
