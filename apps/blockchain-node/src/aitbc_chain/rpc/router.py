from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from aitbc.rate_limiting import rate_limit

from ..config import settings
from ..logger import get_logger
from ..mempool import get_mempool as get_mempool_instance
from .accounts import (
    create_account,
    faucet_request,
    get_account,
    get_account_alias,
    get_balance_breakdown,
    get_state_snapshot,
    reconcile_balance,
)
from .blocks import get_block, get_blocks_range, get_genesis_allocations, get_head, import_block
from .gossip import GetLogsRequest, GetLogsResponse, get_logs
from .subscription import (
    get_lease_status,
    get_subscribers,
    heartbeat,
    register_subscription,
    revoke_subscription,
)
from .sync import export_chain, force_sync, import_chain
from .transactions import (
    TransactionRequest,
    query_transactions,
    submit_marketplace_transaction,
    submit_transaction,
)

_logger = get_logger(__name__)

try:
    from .disputes import (
        authorize_arbitrator,
        file_dispute,
        get_active_disputes,
        get_arbitration_votes,
        get_arbitrator_disputes,
        get_authorized_arbitrators,
        get_dispute,
        get_dispute_evidence,
        get_user_disputes,
        submit_arbitration_vote,
        submit_evidence,
        verify_evidence,
    )
except ImportError:
    _logger.warning("Disputes module not available")
try:
    from ..models.dispute import (
        AuthorizeArbitratorRequest,
        AuthorizeArbitratorResponse,
        FileDisputeRequest,
        FileDisputeResponse,
        GetArbitrationVotesResponse,
        GetDisputeResponse,
        GetEvidenceResponse,
        SubmitArbitrationVoteRequest,
        SubmitArbitrationVoteResponse,
        SubmitEvidenceRequest,
        SubmitEvidenceResponse,
        VerifyEvidenceRequest,
        VerifyEvidenceResponse,
    )
except ImportError:
    _logger.warning("Dispute models not available")
try:
    from .contracts import (
        call_contract,
        create_forum_topic,
        deploy_contract,
        deploy_messaging_contract,
        get_agent_reputation,
        get_forum_topics,
        get_messaging_contract_state,
        get_topic_messages,
        list_contracts,
        moderate_message,
        post_message,
        search_messages,
        verify_contract,
        vote_message,
    )
except ImportError:
    _logger.warning("Contracts module not available")
    from .contracts_stub import (
        call_contract,
        create_forum_topic,
        deploy_contract,
        deploy_messaging_contract,
        get_agent_reputation,
        get_forum_topics,
        get_messaging_contract_state,
        get_topic_messages,
        list_contracts,
        moderate_message,
        post_message,
        search_messages,
        verify_contract,
        vote_message,
    )

try:
    from .islands import (
        BridgeRequestRequest,
        BridgeRequestResponse,
        JoinIslandRequest,
        JoinIslandResponse,
        LeaveIslandRequest,
        LeaveIslandResponse,
        get_island,
        join_island,
        leave_island,
        list_islands,
        request_bridge,
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
    from .bridge import bridge_confirm, bridge_lock, get_bridge_transfer, list_pending_transfers
except ImportError:
    _logger.warning("Bridge module not available")
    bridge_lock = None
    bridge_confirm = None
    get_bridge_transfer = None
    list_pending_transfers = None
try:
    from .staking import (
        cast_governance_vote,
        create_governance_proposal,
        get_agent_identity,
        get_governance_proposal,
        get_staking_info,
        register_agent_identity,
        stake_tokens,
        unstake_tokens,
        verify_agent_identity,
    )
except ImportError:
    _logger.warning("Staking module not available")
    stake_tokens = None
    unstake_tokens = None
    get_staking_info = None
    register_agent_identity = None
    get_agent_identity = None
    verify_agent_identity = None
    create_governance_proposal = None
    cast_governance_vote = None
    get_governance_proposal = None
security = HTTPBearer(auto_error=False)
router = APIRouter()
try:
    from .gpu_resources import *  # noqa: F403
except ImportError:
    _logger.warning("GPU resources module not available")
_last_import_time = 0
_import_lock = asyncio.Lock()


@router.get("/genesis_allocations", summary="Get genesis allocations from blockchain")
@rate_limit(rate=200, per=60)
async def get_genesis_allocations_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get genesis allocations from genesis block metadata for RPC bootstrap"""
    return await get_genesis_allocations(request, chain_id)


@router.get("/head", summary="Get current chain head")
@rate_limit(rate=200, per=60)
async def get_head_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get current chain head"""
    return await get_head(request, chain_id)


@router.get("/height", summary="Get current chain height")
@rate_limit(rate=200, per=60)
async def get_height_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get current chain height"""
    head = await get_head(request, chain_id)
    return {"height": head.get("height", 0)}


@router.get("/blocks/{height}", summary="Get block by height")
@rate_limit(rate=200, per=60)
async def get_block_route(request: Request, height: int, chain_id: str | None = None) -> dict[str, Any]:
    """Get block by height"""
    return await get_block(request, height, chain_id)


@router.get("/blocks-range", summary="Get blocks in height range")
@rate_limit(rate=200, per=60)
async def get_blocks_range_route(
    request: Request, start: int = 0, end: int = 10, include_tx: bool = True, chain_id: str | None = None
) -> dict[str, Any]:
    """Get blocks in a height range"""
    return await get_blocks_range(request, start, end, include_tx, chain_id)


@router.get("/info", summary="Get blockchain information")
@rate_limit(rate=200, per=60)
async def get_info_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get comprehensive blockchain information including transactions, accounts, and genesis parameters"""
    head = await get_head(request, chain_id)
    genesis_params = head.get("genesis_params", {})
    if not genesis_params:
        genesis_params = {
            "block_time_seconds": getattr(settings, "block_time", 2),
            "max_block_size": getattr(settings, "max_block_size", 1000000),
            "difficulty": getattr(settings, "difficulty", 1),
        }
    return {
        "chain_id": getattr(settings, "chain_id", "ait-hub.aitbc.bubuit.net"),
        "height": head.get("height", 0),
        "total_transactions": head.get("total_transactions", 0),
        "total_accounts": head.get("total_accounts", 0),
        "genesis_params": genesis_params,
        "last_block_hash": head.get("hash", ""),
        "timestamp": head.get("timestamp", datetime.now(UTC).isoformat()),
    }


@router.get("/status", summary="Get node status (alias for /info)")
@rate_limit(rate=200, per=60)
async def get_status_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Get node status - alias for /info endpoint"""
    return await get_info_route(request, chain_id)


@router.get("/network-info", summary="Get network information for joining")
@rate_limit(rate=100, per=60)
async def get_network_info_route(request: Request) -> dict[str, Any]:
    """Get network configuration information for open island joining"""
    import os
    import socket
    from pathlib import Path

    env_file = Path("/etc/aitbc/blockchain.env")
    p2p_host = os.getenv("p2p_bind_host", "0.0.0.0")
    p2p_port = os.getenv("p2p_bind_port", "8200")
    p2p_node_id = os.getenv("p2p_node_id", "unknown")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("p2p_bind_host="):
                    p2p_host = line.split("=", 1)[1]
                elif line.startswith("p2p_bind_port="):
                    p2p_port = line.split("=", 1)[1]
                elif line.startswith("p2p_node_id="):
                    p2p_node_id = line.split("=", 1)[1]
    hostname = os.getenv("AITBC_HOSTNAME", socket.gethostname())
    p2p_endpoint = f"{hostname}:{p2p_port}" if p2p_host == "0.0.0.0" else f"{p2p_host}:{p2p_port}"
    chain_id = getattr(settings, "chain_id", "ait-hub.aitbc.bubuit.net")
    supported_chains = getattr(settings, "supported_chains", "ait-mainnet").split(",")
    protocol = os.getenv("AITBC_PROTOCOL", "http")
    if request.url.scheme:
        protocol = request.url.scheme
    contact_email = os.getenv("CONTACT_EMAIL", "andreas.fleckl@bubuit.net")
    rpc_endpoint = f"{protocol}://{hostname}/rpc"
    return {
        "p2p_endpoint": p2p_endpoint,
        "p2p_node_id": p2p_node_id,
        "chain_id": chain_id,
        "network_type": "open_island",
        "supported_chains": supported_chains,
        "connection_instructions": f"Set default_peer_rpc_url={rpc_endpoint} and enable subscription (subscription_enabled=true, subscription_transport=websocket). Blocks are pushed via WebSocket to {rpc_endpoint}/subscribe/ws",
        "rpc_endpoint": rpc_endpoint,
        "api_gateway": f"{protocol}://{hostname}/api",
        "contact_email": contact_email,
        "version": "0.5.4",
    }


@router.post("/importBlock", summary="Import a block")
@rate_limit(rate=50, per=60)
async def import_block_route(request: Request, block_data: dict) -> dict[str, Any]:
    """Import a block into the blockchain"""
    return await import_block(request, block_data)


@router.post("/transaction", summary="Submit transaction")
@rate_limit(rate=50, per=60)
async def submit_transaction_route(request: Request, tx_data: TransactionRequest) -> dict[str, Any]:
    """Submit a new transaction to the mempool"""
    return await submit_transaction(request, tx_data)


@router.get("/mempool", summary="Get pending transactions")
@rate_limit(rate=200, per=60)
async def get_mempool_api_route(request: Request, chain_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Get pending transactions from mempool"""
    # Import locally to avoid circular dependency
    from .transactions import get_mempool

    return await get_mempool(request, chain_id, limit)


@router.post("/transactions/marketplace", summary="Submit marketplace transaction")
@rate_limit(rate=50, per=60)
async def submit_marketplace_transaction_route(request: Request, tx_data: dict[str, Any]) -> dict[str, Any]:
    """Submit a marketplace transaction"""
    return await submit_marketplace_transaction(request, tx_data)


@router.get("/transactions", summary="Query transactions")
@rate_limit(rate=200, per=60)
async def query_transactions_route(
    request: Request,
    transaction_type: str | None = None,
    island_id: str | None = None,
    pair: str | None = None,
    status: str | None = None,
    order_id: str | None = None,
    limit: int | None = 100,
    chain_id: str | None = None,
) -> list[dict[str, Any]]:
    """Query transactions with optional filters"""
    return await query_transactions(request, transaction_type, island_id, pair, status, order_id, limit, chain_id)


@router.get("/account/{address}", summary="Get account information")
@rate_limit(rate=200, per=60)
async def get_account_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get account information"""
    return await get_account(request, address, chain_id)


@router.get("/accounts/{address}", summary="Get account information (alias)")
@rate_limit(rate=200, per=60)
async def get_account_alias_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get account information (alias endpoint)"""
    return await get_account_alias(request, address, chain_id)


@router.get("/state/snapshot", summary="Get full account state snapshot")
@rate_limit(rate=10, per=60)
async def get_state_snapshot_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Return all accounts and the computed state root for follower state sync."""
    return await get_state_snapshot(request, chain_id)


@router.post("/register-account", summary="Create/register a new account on the blockchain")
@rate_limit(rate=100, per=60)
async def create_account_route(request: Request, account_data: dict) -> dict[str, Any]:
    """Create or register a new account on the blockchain"""
    return await create_account(request, account_data)


@router.post("/faucet", summary="Request test tokens from faucet")
@rate_limit(rate=10, per=3600)
async def faucet_request_route(request: Request, faucet_data: dict) -> dict[str, Any]:
    """Request test tokens from the blockchain faucet"""
    return await faucet_request(request, faucet_data)


@router.get("/balance/{address}", summary="Get detailed balance breakdown")
@rate_limit(rate=100, per=60)
async def get_balance_breakdown_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get detailed balance breakdown"""
    return await get_balance_breakdown(request, address, chain_id)


@router.get("/balance/{address}/reconcile", summary="Reconcile balance")
@rate_limit(rate=20, per=60)
async def reconcile_balance_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Reconcile account balance against all recorded operations"""
    return await reconcile_balance(request, address, chain_id)


@router.post("/disputes/file", summary="File a new dispute")
async def file_dispute_route(
    request: FileDisputeRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> FileDisputeResponse:
    """File a new dispute for a marketplace transaction"""
    return await file_dispute(request, http_request, credentials)


@router.post("/disputes/evidence", summary="Submit evidence for a dispute")
async def submit_evidence_route(
    request: SubmitEvidenceRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> SubmitEvidenceResponse:
    """Submit evidence for a dispute"""
    return await submit_evidence(request, http_request, credentials)


@router.post("/disputes/verify-evidence", summary="Verify evidence (arbitrator only)")
async def verify_evidence_route(
    request: VerifyEvidenceRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> VerifyEvidenceResponse:
    """Verify evidence submitted in a dispute"""
    return await verify_evidence(request, http_request, credentials)


@router.post("/disputes/vote", summary="Submit arbitration vote (arbitrator only)")
async def submit_arbitration_vote_route(
    request: SubmitArbitrationVoteRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> SubmitArbitrationVoteResponse:
    """Submit an arbitration vote for a dispute"""
    return await submit_arbitration_vote(request, http_request, credentials)


@router.post("/disputes/arbitrators/authorize", summary="Authorize an arbitrator (admin only)")
async def authorize_arbitrator_route(
    request: AuthorizeArbitratorRequest,
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> AuthorizeArbitratorResponse:
    """Authorize a new arbitrator"""
    return await authorize_arbitrator(request, http_request, credentials)


@router.get("/disputes/active", summary="Get all active disputes")
async def get_active_disputes_route() -> dict[str, Any]:
    """Get all active disputes"""
    return await get_active_disputes()


@router.get("/disputes/arbitrators", summary="Get all authorized arbitrators")
async def get_authorized_arbitrators_route() -> dict[str, Any]:
    """Get all authorized arbitrators"""
    return await get_authorized_arbitrators()


@router.get("/disputes/arbitrators/{arbitrator_address}", summary="Get disputes for an arbitrator")
async def get_arbitrator_disputes_route(arbitrator_address: str) -> dict[str, Any]:
    """Get all disputes assigned to an arbitrator"""
    return await get_arbitrator_disputes(arbitrator_address)


@router.get("/disputes/user/{user_address}", summary="Get disputes for a user")
async def get_user_disputes_route(user_address: str) -> dict[str, Any]:
    """Get all disputes for a specific user"""
    return await get_user_disputes(user_address)


@router.get("/disputes/{dispute_id}", summary="Get dispute details")
async def get_dispute_route(dispute_id: int) -> GetDisputeResponse:
    """Get details of a specific dispute"""
    return await get_dispute(dispute_id)


@router.get("/disputes/{dispute_id}/evidence", summary="Get evidence for a dispute")
async def get_dispute_evidence_route(dispute_id: int) -> list[GetEvidenceResponse]:
    """Get all evidence submitted for a dispute"""
    return await get_dispute_evidence(dispute_id)


@router.get("/disputes/{dispute_id}/votes", summary="Get arbitration votes for a dispute")
async def get_arbitration_votes_route(dispute_id: int) -> list[GetArbitrationVotesResponse]:
    """Get all arbitration votes for a dispute"""
    return await get_arbitration_votes(dispute_id)


@router.post("/contracts/deploy/messaging", summary="Deploy messaging contract")
@rate_limit(rate=50, per=60)
async def deploy_messaging_contract_route(request: Request, deploy_data: dict) -> dict[str, Any]:
    """Deploy the agent messaging contract to the blockchain"""
    return await deploy_messaging_contract(request, deploy_data)


@router.get("/contracts", summary="List deployed contracts")
@rate_limit(rate=200, per=60)
async def list_contracts_route(request: Request) -> dict[str, Any]:
    """List all deployed contracts"""
    return await list_contracts(request)


@router.post("/contracts/deploy", summary="Deploy a smart contract")
@rate_limit(rate=50, per=60)
async def deploy_contract_route(request: Request, deploy_data: dict) -> dict[str, Any]:
    """Deploy a new smart contract to the blockchain"""
    return await deploy_contract(request, deploy_data)


@router.post("/contracts/call", summary="Call a contract method")
@rate_limit(rate=50, per=60)
async def call_contract_route(request: Request, call_data: dict) -> dict[str, Any]:
    """Call a method on a deployed contract"""
    return await call_contract(request, call_data)


@router.post("/contracts/verify", summary="Verify a ZK proof")
@rate_limit(rate=50, per=60)
async def verify_contract_route(request: Request, verify_data: dict) -> dict[str, Any]:
    """Verify a ZK proof against a contract"""
    return await verify_contract(request, verify_data)


@router.get("/contracts/messaging/state", summary="Get messaging contract state")
@rate_limit(rate=200, per=60)
async def get_messaging_contract_state_route(request: Request) -> dict[str, Any]:
    """Get the current state of the messaging contract"""
    return await get_messaging_contract_state(request)


@router.get("/messaging/topics", summary="Get forum topics")
@rate_limit(rate=200, per=60)
async def get_forum_topics_route(
    request: Request, limit: int = 50, offset: int = 0, sort_by: str = "last_activity"
) -> dict[str, Any]:
    """Get list of forum topics"""
    return await get_forum_topics(request, limit, offset, sort_by)


@router.post("/messaging/topics/create", summary="Create forum topic")
@rate_limit(rate=50, per=60)
async def create_forum_topic_route(request: Request, topic_data: dict) -> dict[str, Any]:
    """Create a new forum topic"""
    return await create_forum_topic(request, topic_data)


@router.get("/messaging/topics/{topic_id}/messages", summary="Get topic messages")
@rate_limit(rate=200, per=60)
async def get_topic_messages_route(
    request: Request, topic_id: str, limit: int = 50, offset: int = 0, sort_by: str = "timestamp"
) -> dict[str, Any]:
    """Get messages from a forum topic"""
    return await get_topic_messages(request, topic_id, limit, offset, sort_by)


@router.post("/messaging/messages/post", summary="Post message")
@rate_limit(rate=50, per=60)
async def post_message_route(request: Request, message_data: dict) -> dict[str, Any]:
    """Post a message to a forum topic"""
    return await post_message(request, message_data)


@router.post("/messaging/messages/{message_id}/vote", summary="Vote on message")
@rate_limit(rate=50, per=60)
async def vote_message_route(request: Request, message_id: str, vote_data: dict) -> dict[str, Any]:
    """Vote on a message (upvote/downvote)"""
    return await vote_message(request, message_id, vote_data)


@router.get("/messaging/messages/search", summary="Search messages")
@rate_limit(rate=200, per=60)
async def search_messages_route(request: Request, query: str, limit: int = 50) -> dict[str, Any]:
    """Search messages by content"""
    return await search_messages(request, query, limit)


@router.get("/messaging/agents/{agent_id}/reputation", summary="Get agent reputation")
@rate_limit(rate=200, per=60)
async def get_agent_reputation_route(request: Request, agent_id: str) -> dict[str, Any]:
    """Get agent reputation information"""
    return await get_agent_reputation(request, agent_id)


@router.post("/messaging/messages/{message_id}/moderate", summary="Moderate message")
@rate_limit(rate=50, per=60)
async def moderate_message_route(request: Request, message_id: str, moderation_data: dict) -> dict[str, Any]:
    """Moderate a message (moderator only)"""
    return await moderate_message(request, message_id, moderation_data)


@router.get("/export-chain", summary="Export full chain state")
@rate_limit(rate=200, per=60)
async def export_chain_route(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Export full chain state as JSON for manual synchronization"""
    return await export_chain(request, chain_id)


@router.post("/import-chain", summary="Import chain state")
@rate_limit(rate=50, per=60)
async def import_chain_route(request: Request, import_data: dict) -> dict[str, Any]:
    """Import chain state from JSON for manual synchronization"""
    return await import_chain(request, import_data)


@router.post("/force-sync", summary="Force reorg to specified peer")
@rate_limit(rate=50, per=60)
async def force_sync_route(request: Request, peer_data: dict) -> dict[str, Any]:
    """Force blockchain reorganization to sync with specified peer"""
    return await force_sync(request, peer_data)


@router.post("/eth_getLogs", summary="Query smart contract event logs")
@rate_limit(rate=200, per=60)
async def get_logs_route(request: Request, logs_request: GetLogsRequest, chain_id: str | None = None) -> GetLogsResponse:
    """Query smart contract event logs using eth_getLogs-compatible endpoint"""
    return await get_logs(request, logs_request, chain_id)


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
async def list_islands_route() -> dict[str, Any]:
    """List all islands that the node is a member of"""
    if list_islands is None:
        raise HTTPException(status_code=501, detail="Islands module not available")
    return await list_islands()


@router.get("/islands/{island_id}", summary="Get island details")
@rate_limit(rate=100, per=60)
async def get_island_route(island_id: str) -> dict[str, Any]:
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


@router.post("/bridge/lock", summary="Lock funds for cross-chain transfer")
@rate_limit(rate=20, per=60)
async def bridge_lock_route(request: Request, lock_data: dict) -> dict[str, Any]:
    """Initiate a cross-chain bridge transfer by locking funds"""
    if bridge_lock is None:
        raise HTTPException(status_code=501, detail="Bridge module not available")
    return await bridge_lock(request, lock_data)


@router.post("/bridge/confirm", summary="Confirm and release cross-chain transfer")
@rate_limit(rate=20, per=60)
async def bridge_confirm_route(request: Request, confirm_data: dict) -> dict[str, Any]:
    """Confirm a cross-chain bridge transfer and release funds"""
    if bridge_confirm is None:
        raise HTTPException(status_code=501, detail="Bridge module not available")
    return await bridge_confirm(request, confirm_data)


@router.get("/bridge/transfer/{transfer_id}", summary="Get transfer status")
@rate_limit(rate=100, per=60)
async def get_bridge_transfer_route(request: Request, transfer_id: str) -> dict[str, Any]:
    """Get the status of a cross-chain transfer"""
    if get_bridge_transfer is None:
        raise HTTPException(status_code=501, detail="Bridge module not available")
    return await get_bridge_transfer(request, transfer_id)


@router.get("/bridge/pending", summary="List pending bridge transfers")
@rate_limit(rate=50, per=60)
async def list_pending_transfers_route(request: Request, chain_id: str | None = None) -> list[dict[str, Any]]:
    """List all pending cross-chain transfers"""
    if list_pending_transfers is None:
        raise HTTPException(status_code=501, detail="Bridge module not available")
    return await list_pending_transfers(request, chain_id)


@router.post("/staking/stake", summary="Stake tokens")
@rate_limit(rate=20, per=60)
async def stake_tokens_route(request: Request, stake_data: dict) -> dict[str, Any]:
    """Stake tokens for consensus participation"""
    if stake_tokens is None:
        raise HTTPException(status_code=501, detail="Staking module not available")
    return await stake_tokens(request, stake_data)


@router.post("/staking/unstake", summary="Unstake tokens")
@rate_limit(rate=10, per=60)
async def unstake_tokens_route(request: Request, unstake_data: dict) -> dict[str, Any]:
    """Unstake tokens after lock period expires"""
    if unstake_tokens is None:
        raise HTTPException(status_code=501, detail="Staking module not available")
    return await unstake_tokens(request, unstake_data)


@router.get("/staking/{address}", summary="Get staking info")
@rate_limit(rate=100, per=60)
async def get_staking_info_route(request: Request, address: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get staking information for an address"""
    if get_staking_info is None:
        raise HTTPException(status_code=501, detail="Staking module not available")
    return await get_staking_info(request, address, chain_id)


@router.post("/identity/register", summary="Register agent identity")
@rate_limit(rate=20, per=60)
async def register_agent_identity_route(request: Request, identity_data: dict) -> dict[str, Any]:
    """Register an agent identity on the blockchain"""
    if register_agent_identity is None:
        raise HTTPException(status_code=501, detail="Identity module not available")
    return await register_agent_identity(request, identity_data)


@router.get("/identity/{agent_id}", summary="Get agent identity")
@rate_limit(rate=50, per=60)
async def get_agent_identity_route(request: Request, agent_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get agent identity from blockchain"""
    if get_agent_identity is None:
        raise HTTPException(status_code=501, detail="Identity module not available")
    return await get_agent_identity(request, agent_id, chain_id)


@router.post("/identity/verify", summary="Verify agent identity")
@rate_limit(rate=50, per=60)
async def verify_agent_identity_route(request: Request, verification_data: dict) -> dict[str, Any]:
    """Verify an agent identity on the blockchain"""
    if verify_agent_identity is None:
        raise HTTPException(status_code=501, detail="Identity module not available")
    return await verify_agent_identity(request, verification_data)


@router.post("/governance/proposal", summary="Create governance proposal")
@rate_limit(rate=20, per=60)
async def create_governance_proposal_route(request: Request, proposal_data: dict) -> dict[str, Any]:
    """Create a governance proposal on the blockchain"""
    if create_governance_proposal is None:
        raise HTTPException(status_code=501, detail="Governance module not available")
    return await create_governance_proposal(request, proposal_data)


@router.post("/governance/vote", summary="Cast governance vote")
@rate_limit(rate=50, per=60)
async def cast_governance_vote_route(request: Request, vote_data: dict) -> dict[str, Any]:
    """Cast a vote on a governance proposal"""
    if cast_governance_vote is None:
        raise HTTPException(status_code=501, detail="Governance module not available")
    return await cast_governance_vote(request, vote_data)


@router.get("/governance/proposal/{proposal_id}", summary="Get governance proposal")
@rate_limit(rate=50, per=60)
async def get_governance_proposal_route(request: Request, proposal_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Get a governance proposal from the blockchain"""
    if get_governance_proposal is None:
        raise HTTPException(status_code=501, detail="Governance module not available")
    return await get_governance_proposal(request, proposal_id, chain_id)


@router.post("/mining/start", summary="Start mining")
@rate_limit(rate=10, per=60)
async def start_mining_route(request: Request, mining_data: dict) -> dict[str, Any]:
    """Start mining with specified wallet"""
    miner_address = mining_data.get("miner_address")
    threads = mining_data.get("threads", 1)
    if not miner_address:
        raise HTTPException(status_code=400, detail="miner_address is required")
    if not hasattr(start_mining_route, "miners"):
        start_mining_route.miners = {}  # type: ignore[attr-defined]
    start_mining_route.miners[miner_address] = {
        "address": miner_address,
        "threads": threads,
        "enabled": True,
        "started_at": datetime.now(UTC).isoformat(),
    }
    return {"status": "started", "miner_address": miner_address, "threads": threads, "message": "Mining started successfully"}


@router.post("/mining/stop", summary="Stop mining")
@rate_limit(rate=10, per=60)
async def stop_mining_route(request: Request) -> dict[str, Any]:
    """Stop all mining operations"""
    if hasattr(start_mining_route, "miners"):
        for miner in start_mining_route.miners.values():
            miner["enabled"] = False
            miner["stopped_at"] = datetime.now(UTC).isoformat()
    return {"status": "stopped", "message": "Mining stopped successfully"}


@router.get("/mining/status", summary="Get mining status")
@rate_limit(rate=100, per=60)
async def get_mining_status_route(request: Request) -> dict[str, Any]:
    """Get current mining status"""
    if not hasattr(start_mining_route, "miners"):
        return {"status": "idle", "miners": [], "active_count": 0}
    active_miners = [m for m in start_mining_route.miners.values() if m.get("enabled", False)]
    return {
        "status": "mining" if active_miners else "idle",
        "miners": list(start_mining_route.miners.values()),
        "active_count": len(active_miners),
    }


@router.get("/mining/miners", summary="List active miners")
@rate_limit(rate=100, per=60)
async def list_miners_route(request: Request) -> dict[str, Any]:
    """List all registered miners"""
    if not hasattr(start_mining_route, "miners"):
        return {"miners": [], "count": 0}
    return {"miners": list(start_mining_route.miners.values()), "count": len(start_mining_route.miners)}


@router.post("/subscribe", summary="Register for block subscription with lease")
@rate_limit(rate=10, per=60)
async def subscribe_route(request: dict[str, Any]) -> dict[str, Any]:
    """Register a follower node for block subscription with a lease"""
    return await register_subscription(request)


@router.post("/heartbeat", summary="Extend subscription lease via heartbeat")
@rate_limit(rate=60, per=60)
async def heartbeat_route(request: dict[str, Any]) -> dict[str, Any]:
    """Extend a subscriber's lease via heartbeat"""
    return await heartbeat(request)


@router.get("/lease/{node_id}", summary="Get lease status for a subscriber")
@rate_limit(rate=100, per=60)
async def lease_status_route(node_id: str) -> dict[str, Any]:
    """Check the lease status for a subscriber"""
    return await get_lease_status(node_id)


@router.delete("/lease/{node_id}", summary="Revoke subscription lease")
@rate_limit(rate=10, per=60)
async def revoke_lease_route(node_id: str) -> dict[str, Any]:
    """Revoke a subscriber's lease"""
    return await revoke_subscription(node_id)


@router.get("/subscribers", summary="Get all valid subscribers")
@rate_limit(rate=100, per=60)
async def subscribers_route(chain_id: str | None = None) -> dict[str, Any]:
    """Get all subscribers with valid leases"""
    return await get_subscribers(chain_id)


@router.get("/pending", summary="Get pending transactions")
@rate_limit(rate=100, per=60)
async def get_pending_transactions_route(request: Request, chain_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Get pending transactions from mempool (alias for /mempool)"""
    try:
        mempool = get_mempool_instance()
        pending_txs = mempool.get_pending_transactions(chain_id=chain_id, limit=limit)
        return {"transactions": pending_txs, "count": len(pending_txs)}
    except Exception as e:
        _logger.error("Error getting pending transactions: %s", e)
        return {"transactions": [], "count": 0, "error": str(e)}
