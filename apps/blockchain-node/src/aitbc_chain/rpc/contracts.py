"""
Contract-related RPC endpoints.

Contract deployment, calling, and verification use the on-chain database.
Contract addresses are deterministically derived from the deployer address,
contract name, and deployment timestamp.
"""

import hashlib
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlmodel import select

from aitbc.rate_limiting import rate_limit

from ..base_models import SmartContract
from ..database import session_scope
from ..logger import get_logger
from . import messaging as messaging_reads
from .contract_service import contract_service

_logger = get_logger(__name__)


def _derive_contract_address(deployer: str, name: str, timestamp: int) -> str:
    """Derive a deterministic contract address from deployer, name, and timestamp.

    Similar to Ethereum's CREATE address scheme: hash(deployer || nonce).
    """
    data = f"{deployer.lower()}:{name.lower()}:{timestamp}".encode()
    return "0x" + hashlib.sha256(data).hexdigest()[:40]


@rate_limit(rate=50, per=60)
async def deploy_messaging_contract(request: Request, deploy_data: dict[str, Any]) -> dict[str, Any]:
    """Retired: there is no messaging contract — forum messages are MESSAGE transactions."""
    raise messaging_reads.messaging_not_on_chain("deploy/messaging")


@rate_limit(rate=200, per=60)
async def list_contracts(request: Request) -> dict[str, Any]:
    """List all deployed contracts from the database"""
    return contract_service.list_contracts()


@rate_limit(rate=50, per=60)
async def deploy_contract(request: Request, deploy_data: dict[str, Any]) -> dict[str, Any]:
    """Deploy a new smart contract to the blockchain.

    Stores the contract in the on-chain database with a deterministically
    derived address.
    """
    contract_name = deploy_data.get("name")
    contract_type = deploy_data.get("type", "zk-verifier")
    deployer = deploy_data.get("deployer", "0x0000000000000000000000000000000000000000")
    bytecode = deploy_data.get("bytecode", "")
    abi = deploy_data.get("abi", {})
    chain_id = deploy_data.get("chain_id", "")

    if not contract_name:
        return {"success": False, "error": "Contract name is required"}

    # Derive a deterministic contract address
    timestamp = int(time.time())
    contract_address = _derive_contract_address(deployer, contract_name, timestamp)

    # Store in database
    with session_scope(chain_id) as session:
        contract = SmartContract(
            chain_id=chain_id,
            address=contract_address,
            name=contract_name,
            contract_type=contract_type,
            deployer=deployer,
            bytecode=bytecode,
            abi=abi if isinstance(abi, dict) else {},
            state={},
            status="deployed",
            deployed_at=datetime.now(UTC),
        )
        session.add(contract)
        session.commit()

    _logger.info("Deployed contract %s (%s) at %s", contract_name, contract_type, contract_address)

    return {
        "success": True,
        "contract_address": contract_address,
        "name": contract_name,
        "type": contract_type,
        "status": "deployed",
        "deployed_at": datetime.now(UTC).isoformat(),
    }


@rate_limit(rate=50, per=60)
async def call_contract(request: Request, call_data: dict[str, Any]) -> dict[str, Any]:
    """Call a method on a deployed contract.

    Looks up the contract in the database and returns its stored state.
    Read-only calls return the current state value for the requested method.
    """
    contract_address = call_data.get("address")
    method = call_data.get("method")
    params = call_data.get("params", {})
    chain_id = call_data.get("chain_id", "")

    if not contract_address:
        return {"success": False, "error": "Contract address is required"}
    if not method:
        return {"success": False, "error": "Method name is required"}

    with session_scope(chain_id) as session:
        stmt = select(SmartContract).where(
            SmartContract.address == contract_address,
            SmartContract.status == "deployed",
        )
        if chain_id:
            stmt = stmt.where(SmartContract.chain_id == chain_id)

        contract = session.exec(stmt).first()
        if not contract:
            return {"success": False, "error": f"Contract not found at address {contract_address}"}

        # Return the stored state for the requested method
        state_value = contract.state.get(method) if contract.state else None
        abi_entry = contract.abi.get(method) if contract.abi else None

        return {
            "success": True,
            "result": state_value,
            "address": contract_address,
            "method": method,
            "params": params,
            "abi": abi_entry,
        }


@rate_limit(rate=50, per=60)
async def verify_contract(request: Request, verify_data: dict[str, Any]) -> dict[str, Any]:
    """Verify a ZK proof against a contract.

    Checks that the contract exists and is deployed. Returns the actual
    verification status — does not hardcode 'valid: True'.
    """
    contract_address = verify_data.get("address")
    proof = verify_data.get("proof")
    chain_id = verify_data.get("chain_id", "")

    if not contract_address:
        return {"success": False, "error": "Contract address is required"}

    if not proof:
        return {"success": False, "error": "Proof data is required"}

    with session_scope(chain_id) as session:
        stmt = select(SmartContract).where(
            SmartContract.address == contract_address,
            SmartContract.status == "deployed",
        )
        if chain_id:
            stmt = stmt.where(SmartContract.chain_id == chain_id)

        contract = session.exec(stmt).first()
        if not contract:
            return {
                "success": False,
                "error": f"Contract not found at address {contract_address}",
                "result": {"valid": False, "reason": "contract_not_found"},
            }

        # Check if the contract type supports ZK verification
        if contract.contract_type != "zk-verifier":
            return {
                "success": True,
                "result": {
                    "valid": False,
                    "reason": f"Contract type '{contract.contract_type}' does not support ZK proof verification",
                    "address": contract_address,
                },
            }

        # ZK proof verification requires a real ZK verifier implementation, which this node
        # does not have. Return an honest result rather than accepting the proof.
        #
        # This refusal is unconditional. An earlier comment here said "the
        # enable_zk_proof_verification feature flag is currently disabled", which read as
        # though a flag governed it — nothing did: that flag lived in feature_flags.json,
        # which no code has read since aitbc/feature_flags.py was deleted in v0.10.9. The
        # file was removed in v0.23 (V23-32). Behaviour is unchanged; only the explanation
        # was wrong, and a wrong explanation of correct behaviour is how the behaviour gets
        # "restored" to something worse by someone who believes the flag is the real gate.
        return {
            "success": True,
            "result": {
                "valid": False,
                "reason": "ZK proof verification is not enabled on this node",
                "address": contract_address,
                "proof_received": bool(proof),
            },
        }


# -- Forum messaging (MSG-1) -------------------------------------------------
# Reads are repointed to the chain-derived index (rpc/messaging.py). Writes
# that mutated a process-local singleton now answer 501: posting is a signed
# MESSAGE transaction, and votes/moderation/reputation are MSG-2 scope.


@rate_limit(rate=200, per=60)
async def get_messaging_contract_state(request: Request, chain_id: str | None = None) -> dict[str, Any]:
    """Forum totals derived from sealed MESSAGE transactions."""
    result: dict[str, Any] = await messaging_reads.messaging_state(request, chain_id=chain_id)
    return result


@rate_limit(rate=200, per=60)
async def get_forum_topics(
    request: Request, limit: int = 50, offset: int = 0, sort_by: str = "last_activity"
) -> dict[str, Any]:
    """List forum topics (chain-derived; implicit topics, no creation call)."""
    topics: dict[str, Any] = await messaging_reads.forum_topics(request, limit=limit, offset=offset, sort_by=sort_by)
    return topics


@rate_limit(rate=50, per=60)
async def create_forum_topic(request: Request, topic_data: dict[str, Any]) -> dict[str, Any]:
    """Retired: topics are implicit — the first signed post creates them."""
    raise messaging_reads.messaging_not_on_chain("topics/create")


@rate_limit(rate=200, per=60)
async def get_topic_messages(
    request: Request, topic_id: str, limit: int = 50, offset: int = 0, sort_by: str = "timestamp"
) -> dict[str, Any]:
    """Get messages for a topic slug (chain-derived)."""
    messages: dict[str, Any] = await messaging_reads.forum_topic_messages(
        request, topic_id, limit=limit, offset=offset, sort_by=sort_by
    )
    return messages


@rate_limit(rate=50, per=60)
async def post_message(request: Request, message_data: dict[str, Any]) -> dict[str, Any]:
    """Retired: post by signing a MESSAGE transaction, not via RPC mutation."""
    raise messaging_reads.messaging_not_on_chain("messages/post")


@rate_limit(rate=50, per=60)
async def vote_message(request: Request, message_id: str, vote_data: dict[str, Any]) -> dict[str, Any]:
    """Not implemented: on-chain votes are MSG-2 scope."""
    raise messaging_reads.messaging_not_on_chain("votes (MSG-2 scope)")


@rate_limit(rate=200, per=60)
async def search_messages(request: Request, query: str, limit: int = 50) -> dict[str, Any]:
    """Search forum message bodies (chain-derived, bounded)."""
    found: dict[str, Any] = await messaging_reads.forum_search(request, query=query, limit=limit)
    return found


@rate_limit(rate=200, per=60)
async def get_agent_reputation(request: Request, agent_id: str) -> dict[str, Any]:
    """Not implemented: reputation is MSG-2 scope; agent_id was dropped entirely."""
    raise messaging_reads.messaging_not_on_chain("reputation (MSG-2 scope)")


@rate_limit(rate=50, per=60)
async def moderate_message(request: Request, message_id: str, moderation_data: dict[str, Any]) -> dict[str, Any]:
    """Not implemented: on-chain moderation is MSG-2 scope."""
    raise messaging_reads.messaging_not_on_chain("moderation (MSG-2 scope)")
