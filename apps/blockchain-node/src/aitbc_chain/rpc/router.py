from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select, delete

from ..database import session_scope, get_engine
from ..gossip import gossip_broker
from ..mempool import get_mempool
from ..metrics import metrics_registry
from ..models import Account, Block, Receipt, Transaction
from ..logger import get_logger
from ..sync import ChainSync
from .auth import get_authenticated_address
from .utils import (
    set_poa_proposer,
    get_poa_proposer,
    get_chain_id,
    validate_chain_id,
    get_supported_chains,
    get_chain_db,
    normalize_transaction_data,
)

from aitbc.rate_limiting import rate_limit

_logger = get_logger(__name__)

# Import domain modules
from .blocks import (
    get_genesis_allocations,
    get_head,
    get_block,
    get_blocks_range,
    import_block,
)
from .transactions import (
    submit_transaction,
    get_mempool,
    submit_marketplace_transaction,
    query_transactions,
    TransactionRequest,
)
from .accounts import (
    get_account,
    get_account_alias,
    get_account_details,
    create_account,
    faucet_request,
    get_balance_breakdown,
    reconcile_balance,
)
try:
    from .disputes import (
        file_dispute,
        submit_evidence,
        verify_evidence,
        submit_arbitration_vote,
        authorize_arbitrator,
        get_active_disputes,
        get_authorized_arbitrators,
        get_arbitrator_disputes,
        get_user_disputes,
        get_dispute,
        get_dispute_evidence,
        get_arbitration_votes,
    )
except ImportError:
    _logger.warning("Disputes module not available")
try:
    from ..models.dispute import (
        FileDisputeRequest,
        FileDisputeResponse,
        SubmitEvidenceRequest,
        SubmitEvidenceResponse,
        VerifyEvidenceRequest,
        VerifyEvidenceResponse,
        SubmitArbitrationVoteRequest,
        SubmitArbitrationVoteResponse,
        AuthorizeArbitratorRequest,
        AuthorizeArbitratorResponse,
        GetDisputeResponse,
        GetEvidenceResponse,
        GetArbitrationVotesResponse,
    )
except ImportError:
    _logger.warning("Dispute models not available")
try:
    from .contracts import (
        deploy_messaging_contract,
        list_contracts,
        deploy_contract,
        call_contract,
        verify_contract,
        get_messaging_contract_state,
        get_forum_topics,
        create_forum_topic,
        get_topic_messages,
        post_message,
        vote_message,
        search_messages,
        get_agent_reputation,
        moderate_message,
    )
except ImportError:
    _logger.warning("Contracts module not available")
from .sync import (
    export_chain,
    import_chain,
    force_sync,
)
from .gossip import (
    get_logs,
    GetLogsRequest,
    GetLogsResponse,
)
try:
    from .islands import (
        join_island,
        leave_island,
        list_islands,
        get_island,
        request_bridge,
        JoinIslandRequest,
        JoinIslandResponse,
        LeaveIslandRequest,
        LeaveIslandResponse,
        BridgeRequestRequest,
        BridgeRequestResponse,
    )
except ImportError:
    _logger.warning("Islands module not available")
    join_island = None
    leave_island = None
    list_islands = None
    get_island = None
    request_bridge = None
    JoinIslandRequest = None
    JoinIslandResponse = None
    LeaveIslandRequest = None
    LeaveIslandResponse = None
    BridgeRequestRequest = None
    BridgeRequestResponse = None
try:
    from .bridge import (
        bridge_lock,
        bridge_confirm,
        get_bridge_transfer,
        list_pending_transfers,
    )
except ImportError:
    _logger.warning("Bridge module not available")
    bridge_lock = None
    bridge_confirm = None
    get_bridge_transfer = None
    list_pending_transfers = None
try:
    from .staking import (
        stake_tokens,
        unstake_tokens,
        get_staking_info,
    )
except ImportError:
    _logger.warning("Staking module not available")
    stake_tokens = None
    unstake_tokens = None
    get_staking_info = None

# Security scheme for authentication
security = HTTPBearer(auto_error=False)

router = APIRouter()

# Global rate limiter for importBlock
_last_import_time = 0
_import_lock = asyncio.Lock()


# ============================================================================
# BLOCK ENDPOINTS
# ============================================================================

@router.get("/genesis_allocations", summary="Get genesis allocations from blockchain")
@rate_limit(rate=200, per=60)
async def get_genesis_allocations_route(
    request: Request, chain_id: str = None
) -> Dict[str, Any]:
    """Get genesis allocations from genesis block metadata for RPC bootstrap"""
    return await get_genesis_allocations(request, chain_id)


@router.get("/head", summary="Get current chain head")
@rate_limit(rate=200, per=60)
async def get_head_route(
    request: Request, chain_id: str = None
) -> Dict[str, Any]:
    """Get current chain head"""
    return await get_head(request, chain_id)


@router.get("/blocks/{height}", summary="Get block by height")
@rate_limit(rate=200, per=60)
async def get_block_route(
    request: Request, height: int, chain_id: str = None
) -> Dict[str, Any]:
    """Get block by height"""
    return await get_block(request, height, chain_id)


@router.get("/blocks-range", summary="Get blocks in height range")
@rate_limit(rate=200, per=60)
async def get_blocks_range_route(
    request: Request, start: int = 0, end: int = 10, include_tx: bool = True, chain_id: str = None
) -> Dict[str, Any]:
    """Get blocks in a height range"""
    return await get_blocks_range(request, start, end, include_tx, chain_id)


@router.post("/importBlock", summary="Import a block")
@rate_limit(rate=50, per=60)
async def import_block_route(
    request: Request, block_data: dict
) -> Dict[str, Any]:
    """Import a block into the blockchain"""
    return await import_block(request, block_data)


# ============================================================================
# TRANSACTION ENDPOINTS
# ============================================================================

@router.post("/transaction", summary="Submit transaction")
@rate_limit(rate=50, per=60)
async def submit_transaction_route(
    request: Request, tx_data: TransactionRequest
) -> Dict[str, Any]:
    """Submit a new transaction to the mempool"""
    return await submit_transaction(request, tx_data)


@router.get("/mempool", summary="Get pending transactions")
@rate_limit(rate=200, per=60)
async def get_mempool_route(
    request: Request, chain_id: str = None, limit: int = 100
) -> Dict[str, Any]:
    """Get pending transactions from mempool"""
    return await get_mempool(request, chain_id, limit)


@router.post("/transactions/marketplace", summary="Submit marketplace transaction")
@rate_limit(rate=50, per=60)
async def submit_marketplace_transaction_route(
    request: Request, tx_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Submit a marketplace transaction"""
    return await submit_marketplace_transaction(request, tx_data)


@router.get("/transactions", summary="Query transactions")
@rate_limit(rate=200, per=60)
async def query_transactions_route(
    request: Request,
    transaction_type: Optional[str] = None,
    island_id: Optional[str] = None,
    pair: Optional[str] = None,
    status: Optional[str] = None,
    order_id: Optional[str] = None,
    limit: Optional[int] = 100,
    chain_id: str = None
) -> List[Dict[str, Any]]:
    """Query transactions with optional filters"""
    return await query_transactions(
        request, transaction_type, island_id, pair, status, order_id, limit, chain_id
    )


# ============================================================================
# ACCOUNT ENDPOINTS
# ============================================================================

@router.get("/account/{address}", summary="Get account information")
@rate_limit(rate=200, per=60)
async def get_account_route(
    request: Request, address: str, chain_id: str = None
) -> Dict[str, Any]:
    """Get account information"""
    return await get_account(request, address, chain_id)


@router.get("/accounts/{address}", summary="Get account information (alias)")
@rate_limit(rate=200, per=60)
async def get_account_alias_route(
    request: Request, address: str, chain_id: str = None
) -> Dict[str, Any]:
    """Get account information (alias endpoint)"""
    return await get_account_alias(request, address, chain_id)


@router.post("/register-account", summary="Create/register a new account on the blockchain")
@rate_limit(rate=100, per=60)
async def create_account_route(
    request: Request,
    account_data: dict
) -> Dict[str, Any]:
    """Create or register a new account on the blockchain"""
    return await create_account(request, account_data)


@router.post("/faucet", summary="Request test tokens from faucet")
@rate_limit(rate=10, per=3600)
async def faucet_request_route(
    request: Request,
    faucet_data: dict
) -> Dict[str, Any]:
    """Request test tokens from the blockchain faucet"""
    return await faucet_request(request, faucet_data)


@router.get("/balance/{address}", summary="Get detailed balance breakdown")
@rate_limit(rate=100, per=60)
async def get_balance_breakdown_route(
    request: Request,
    address: str,
    chain_id: str = None
) -> Dict[str, Any]:
    """Get detailed balance breakdown"""
    return await get_balance_breakdown(request, address, chain_id)


@router.get("/balance/{address}/reconcile", summary="Reconcile balance")
@rate_limit(rate=20, per=60)
async def reconcile_balance_route(
    request: Request,
    address: str,
    chain_id: str = None
) -> Dict[str, Any]:
    """Reconcile account balance against all recorded operations"""
    return await reconcile_balance(request, address, chain_id)


# ============================================================================
# DISPUTE ENDPOINTS
# ============================================================================

@router.post("/disputes/file", summary="File a new dispute")
async def file_dispute_route(
    request: FileDisputeRequest,
    http_request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> FileDisputeResponse:
    """File a new dispute for a marketplace transaction"""
    return await file_dispute(request, http_request, credentials)


@router.post("/disputes/evidence", summary="Submit evidence for a dispute")
async def submit_evidence_route(
    request: SubmitEvidenceRequest,
    http_request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> SubmitEvidenceResponse:
    """Submit evidence for a dispute"""
    return await submit_evidence(request, http_request, credentials)


@router.post("/disputes/verify-evidence", summary="Verify evidence (arbitrator only)")
async def verify_evidence_route(
    request: VerifyEvidenceRequest,
    http_request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> VerifyEvidenceResponse:
    """Verify evidence submitted in a dispute"""
    return await verify_evidence(request, http_request, credentials)


@router.post("/disputes/vote", summary="Submit arbitration vote (arbitrator only)")
async def submit_arbitration_vote_route(
    request: SubmitArbitrationVoteRequest,
    http_request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> SubmitArbitrationVoteResponse:
    """Submit an arbitration vote for a dispute"""
    return await submit_arbitration_vote(request, http_request, credentials)


@router.post("/disputes/arbitrators/authorize", summary="Authorize an arbitrator (admin only)")
async def authorize_arbitrator_route(
    request: AuthorizeArbitratorRequest,
    http_request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthorizeArbitratorResponse:
    """Authorize a new arbitrator"""
    return await authorize_arbitrator(request, http_request, credentials)


@router.get("/disputes/active", summary="Get all active disputes")
async def get_active_disputes_route() -> Dict[str, Any]:
    """Get all active disputes"""
    return await get_active_disputes()


@router.get("/disputes/arbitrators", summary="Get all authorized arbitrators")
async def get_authorized_arbitrators_route() -> Dict[str, Any]:
    """Get all authorized arbitrators"""
    return await get_authorized_arbitrators()


@router.get("/disputes/arbitrators/{arbitrator_address}", summary="Get disputes for an arbitrator")
async def get_arbitrator_disputes_route(arbitrator_address: str) -> Dict[str, Any]:
    """Get all disputes assigned to an arbitrator"""
    return await get_arbitrator_disputes(arbitrator_address)


@router.get("/disputes/user/{user_address}", summary="Get disputes for a user")
async def get_user_disputes_route(user_address: str) -> Dict[str, Any]:
    """Get all disputes for a specific user"""
    return await get_user_disputes(user_address)


@router.get("/disputes/{dispute_id}", summary="Get dispute details")
async def get_dispute_route(dispute_id: int) -> GetDisputeResponse:
    """Get details of a specific dispute"""
    return await get_dispute(dispute_id)


@router.get("/disputes/{dispute_id}/evidence", summary="Get evidence for a dispute")
async def get_dispute_evidence_route(dispute_id: int) -> List[GetEvidenceResponse]:
    """Get all evidence submitted for a dispute"""
    return await get_dispute_evidence(dispute_id)


@router.get("/disputes/{dispute_id}/votes", summary="Get arbitration votes for a dispute")
async def get_arbitration_votes_route(dispute_id: int) -> List[GetArbitrationVotesResponse]:
    """Get all arbitration votes for a dispute"""
    return await get_arbitration_votes(dispute_id)


# ============================================================================
# CONTRACT ENDPOINTS
# ============================================================================

@router.post("/contracts/deploy/messaging", summary="Deploy messaging contract")
@rate_limit(rate=50, per=60)
async def deploy_messaging_contract_route(
    request: Request, deploy_data: dict
) -> Dict[str, Any]:
    """Deploy the agent messaging contract to the blockchain"""
    return await deploy_messaging_contract(request, deploy_data)


@router.get("/contracts", summary="List deployed contracts")
@rate_limit(rate=200, per=60)
async def list_contracts_route(
    request: Request
) -> Dict[str, Any]:
    """List all deployed contracts"""
    return await list_contracts(request)


@router.post("/contracts/deploy", summary="Deploy a smart contract")
@rate_limit(rate=50, per=60)
async def deploy_contract_route(
    request: Request, deploy_data: dict
) -> Dict[str, Any]:
    """Deploy a new smart contract to the blockchain"""
    return await deploy_contract(request, deploy_data)


@router.post("/contracts/call", summary="Call a contract method")
@rate_limit(rate=50, per=60)
async def call_contract_route(
    request: Request, call_data: dict
) -> Dict[str, Any]:
    """Call a method on a deployed contract"""
    return await call_contract(request, call_data)


@router.post("/contracts/verify", summary="Verify a ZK proof")
@rate_limit(rate=50, per=60)
async def verify_contract_route(
    request: Request, verify_data: dict
) -> Dict[str, Any]:
    """Verify a ZK proof against a contract"""
    return await verify_contract(request, verify_data)


@router.get("/contracts/messaging/state", summary="Get messaging contract state")
@rate_limit(rate=200, per=60)
async def get_messaging_contract_state_route(
    request: Request
) -> Dict[str, Any]:
    """Get the current state of the messaging contract"""
    return await get_messaging_contract_state(request)


@router.get("/messaging/topics", summary="Get forum topics")
@rate_limit(rate=200, per=60)
async def get_forum_topics_route(
    request: Request, limit: int = 50, offset: int = 0, sort_by: str = "last_activity"
) -> Dict[str, Any]:
    """Get list of forum topics"""
    return await get_forum_topics(request, limit, offset, sort_by)


@router.post("/messaging/topics/create", summary="Create forum topic")
@rate_limit(rate=50, per=60)
async def create_forum_topic_route(
    request: Request, topic_data: dict
) -> Dict[str, Any]:
    """Create a new forum topic"""
    return await create_forum_topic(request, topic_data)


@router.get("/messaging/topics/{topic_id}/messages", summary="Get topic messages")
@rate_limit(rate=200, per=60)
async def get_topic_messages_route(
    request: Request, topic_id: str, limit: int = 50, offset: int = 0, sort_by: str = "timestamp"
) -> Dict[str, Any]:
    """Get messages from a forum topic"""
    return await get_topic_messages(request, topic_id, limit, offset, sort_by)


@router.post("/messaging/messages/post", summary="Post message")
@rate_limit(rate=50, per=60)
async def post_message_route(
    request: Request, message_data: dict
) -> Dict[str, Any]:
    """Post a message to a forum topic"""
    return await post_message(request, message_data)


@router.post("/messaging/messages/{message_id}/vote", summary="Vote on message")
@rate_limit(rate=50, per=60)
async def vote_message_route(
    request: Request, message_id: str, vote_data: dict
) -> Dict[str, Any]:
    """Vote on a message (upvote/downvote)"""
    return await vote_message(request, message_id, vote_data)


@router.get("/messaging/messages/search", summary="Search messages")
@rate_limit(rate=200, per=60)
async def search_messages_route(
    request: Request, query: str, limit: int = 50
) -> Dict[str, Any]:
    """Search messages by content"""
    return await search_messages(request, query, limit)


@router.get("/messaging/agents/{agent_id}/reputation", summary="Get agent reputation")
@rate_limit(rate=200, per=60)
async def get_agent_reputation_route(
    request: Request, agent_id: str
) -> Dict[str, Any]:
    """Get agent reputation information"""
    return await get_agent_reputation(request, agent_id)


@router.post("/messaging/messages/{message_id}/moderate", summary="Moderate message")
@rate_limit(rate=50, per=60)
async def moderate_message_route(
    request: Request, message_id: str, moderation_data: dict
) -> Dict[str, Any]:
    """Moderate a message (moderator only)"""
    return await moderate_message(request, message_id, moderation_data)


# ============================================================================
# SYNC ENDPOINTS
# ============================================================================

@router.get("/export-chain", summary="Export full chain state")
@rate_limit(rate=200, per=60)
async def export_chain_route(
    request: Request, chain_id: str = None
) -> Dict[str, Any]:
    """Export full chain state as JSON for manual synchronization"""
    return await export_chain(request, chain_id)


@router.post("/import-chain", summary="Import chain state")
@rate_limit(rate=50, per=60)
async def import_chain_route(
    request: Request, import_data: dict
) -> Dict[str, Any]:
    """Import chain state from JSON for manual synchronization"""
    return await import_chain(request, import_data)


@router.post("/force-sync", summary="Force reorg to specified peer")
@rate_limit(rate=50, per=60)
async def force_sync_route(
    request: Request, peer_data: dict
) -> Dict[str, Any]:
    """Force blockchain reorganization to sync with specified peer"""
    return await force_sync(request, peer_data)


# ============================================================================
# GOSSIP ENDPOINTS
# ============================================================================

@router.post("/eth_getLogs", summary="Query smart contract event logs")
@rate_limit(rate=200, per=60)
async def get_logs_route(
    request: Request,
    logs_request: GetLogsRequest,
    chain_id: Optional[str] = None
) -> GetLogsResponse:
    """Query smart contract event logs using eth_getLogs-compatible endpoint"""
    return await get_logs(request, logs_request, chain_id)


# ============================================================================
# ISLAND ENDPOINTS
# ============================================================================

@router.post("/islands/join", summary="Join an island")
async def join_island_route(request: JoinIslandRequest) -> JoinIslandResponse:
    """Join an island for edge compute operations"""
    if join_island is None:
        raise HTTPException(status_code=501, detail="Islands module not available")
    return await join_island(request)


@router.post("/islands/leave", summary="Leave an island")
async def leave_island_route(request: LeaveIslandRequest) -> LeaveIslandResponse:
    """Leave an island"""
    if leave_island is None:
        raise HTTPException(status_code=501, detail="Islands module not available")
    return await leave_island(request)


@router.get("/islands", summary="List all islands")
@rate_limit(rate=100, per=60)
async def list_islands_route() -> Dict[str, Any]:
    """List all islands that the node is a member of"""
    if list_islands is None:
        raise HTTPException(status_code=501, detail="Islands module not available")
    return await list_islands()


@router.get("/islands/{island_id}", summary="Get island details")
@rate_limit(rate=100, per=60)
async def get_island_route(island_id: str) -> Dict[str, Any]:
    """Get details about a specific island"""
    if get_island is None:
        raise HTTPException(status_code=501, detail="Islands module not available")
    return await get_island(island_id)


@router.post("/islands/bridge", summary="Request a bridge to another island")
async def request_bridge_route(request: BridgeRequestRequest) -> BridgeRequestResponse:
    """Request a bridge to another island for cross-island communication"""
    if request_bridge is None:
        raise HTTPException(status_code=501, detail="Islands module not available")
    return await request_bridge(request)


# ============================================================================
# BRIDGE ENDPOINTS
# ============================================================================

@router.post("/bridge/lock", summary="Lock funds for cross-chain transfer")
@rate_limit(rate=20, per=60)
async def bridge_lock_route(
    request: Request,
    lock_data: dict
) -> Dict[str, Any]:
    """Initiate a cross-chain bridge transfer by locking funds"""
    if bridge_lock is None:
        raise HTTPException(status_code=501, detail="Bridge module not available")
    return await bridge_lock(request, lock_data)


@router.post("/bridge/confirm", summary="Confirm and release cross-chain transfer")
@rate_limit(rate=20, per=60)
async def bridge_confirm_route(
    request: Request,
    confirm_data: dict
) -> Dict[str, Any]:
    """Confirm a cross-chain bridge transfer and release funds"""
    if bridge_confirm is None:
        raise HTTPException(status_code=501, detail="Bridge module not available")
    return await bridge_confirm(request, confirm_data)


@router.get("/bridge/transfer/{transfer_id}", summary="Get transfer status")
@rate_limit(rate=100, per=60)
async def get_bridge_transfer_route(
    request: Request,
    transfer_id: str
) -> Dict[str, Any]:
    """Get the status of a cross-chain transfer"""
    if get_bridge_transfer is None:
        raise HTTPException(status_code=501, detail="Bridge module not available")
    return await get_bridge_transfer(request, transfer_id)


@router.get("/bridge/pending", summary="List pending bridge transfers")
@rate_limit(rate=50, per=60)
async def list_pending_transfers_route(
    request: Request,
    chain_id: str = None
) -> List[Dict[str, Any]]:
    """List all pending cross-chain transfers"""
    if list_pending_transfers is None:
        raise HTTPException(status_code=501, detail="Bridge module not available")
    return await list_pending_transfers(request, chain_id)


# ============================================================================
# STAKING ENDPOINTS
# ============================================================================

@router.post("/staking/stake", summary="Stake tokens")
@rate_limit(rate=20, per=60)
async def stake_tokens_route(
    request: Request,
    stake_data: dict
) -> Dict[str, Any]:
    """Stake tokens for consensus participation"""
    if stake_tokens is None:
        raise HTTPException(status_code=501, detail="Staking module not available")
    return await stake_tokens(request, stake_data)


@router.post("/staking/unstake", summary="Unstake tokens")
@rate_limit(rate=10, per=60)
async def unstake_tokens_route(
    request: Request,
    unstake_data: dict
) -> Dict[str, Any]:
    """Unstake tokens after lock period expires"""
    if unstake_tokens is None:
        raise HTTPException(status_code=501, detail="Staking module not available")
    return await unstake_tokens(request, unstake_data)


@router.get("/staking/{address}", summary="Get staking info")
@rate_limit(rate=100, per=60)
async def get_staking_info_route(
    request: Request,
    address: str,
    chain_id: str = None
) -> Dict[str, Any]:
    """Get staking information for an address"""
    if get_staking_info is None:
        raise HTTPException(status_code=501, detail="Staking module not available")
    return await get_staking_info(request, address, chain_id)
