"""Governance CLI commands (v0.7.3).

Provides commands for on-chain governance operations:
- ``governance propose`` — create a governance proposal
- ``governance vote`` — cast a vote on a proposal
- ``governance list`` — list proposals (with optional status filter)
- ``governance execute`` — execute a passed proposal after timelock
- ``governance status`` — get governance service status
- ``governance get`` — get a specific proposal by ID

These commands talk to the governance service REST API (port 8105)
rather than non-existent blockchain RPC endpoints. The governance
service handles on-chain tx submission when ``enable_onchain_submission``
is enabled in its config.
"""

import json
import uuid

import click

from ..config import get_config
from ..utils import error, output
from ..utils.http_client import AITBCHTTPClient, NetworkError

GOVERNANCE_SERVICE_URL = "http://localhost:8105"


def _governance_rpc(ctx: click.Context) -> tuple[AITBCHTTPClient, str]:
    """Return an RPC client for the node's transaction endpoint + chain_id."""
    from aitbc_cli.commands.wallet.staking import _get_chain_id, _get_rpc_url

    rpc_url = _get_rpc_url(ctx)
    return AITBCHTTPClient(base_url=rpc_url, timeout=10), _get_chain_id(rpc_url)


def _get_governance_account(http_client: AITBCHTTPClient, address: str, chain_id: str) -> dict:
    """Fetch the on-chain account (nonce + balance) for the signing address."""
    try:
        return http_client.get(f"/rpc/account/{address}?chain_id={chain_id}")
    except Exception:
        return {}


def _sign_governance_tx(
    http_client: AITBCHTTPClient,
    chain_id: str,
    private_key: str,
    signer_address: str,
    tx_type: str,
    payload: dict,
    account: dict | None = None,
) -> dict:
    """Build and wallet-sign a governance tx for relay by the service (GAP-50).

    The service holds no per-user keys; the wallet signs here and the service
    verifies recover(signer) == from == to before relaying to /rpc/transaction.
    Signed bytes mirror ``submit_governance_tx``: canonical JSON of the signed
    fields (from/to/amount/fee/nonce/payload/type/chain_id), keccak, secp256k1.
    """
    from aitbc.crypto.signature_recovery import canonical_address
    from aitbc.utils.units import DEFAULT_TX_FEE_UNITS
    from aitbc_cli.commands.wallet.staking import _sign_transaction

    address = canonical_address(signer_address)
    if account is None:
        account = _get_governance_account(http_client, address, chain_id)
    tx = {
        "from": address,
        "to": address,
        "amount": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": int(account.get("nonce", 0) or 0),
        "payload": {"to": address, "amount": 0, "type": tx_type, **payload, "chain_id": chain_id},
        "type": tx_type,
        "chain_id": chain_id,
    }
    tx["signature"] = _sign_transaction({"private_key": private_key}, tx)
    return tx


def _wallet_signer(ctx: click.Context, wallet_name: str | None, password: str | None) -> tuple[str, str] | None:
    """Resolve the signing wallet when --wallet/AITBC_DEFAULT_WALLET is set."""
    from ..utils.agent_signing import load_signing_wallet

    try:
        return load_signing_wallet(ctx, wallet_name, password)
    except Exception as e:
        raise click.ClickException(str(e)) from e


def _get_client(ctx: click.Context | None = None, url: str | None = None) -> AITBCHTTPClient:
    """Create an HTTP client for the governance service."""
    import os

    base_url: str = url or os.getenv("GOVERNANCE_SERVICE_URL") or GOVERNANCE_SERVICE_URL
    if ctx is not None and not url:
        config = ctx.obj.get("config") or get_config()
        if getattr(config, "governance_service_url", ""):
            base_url = config.governance_service_url
    return AITBCHTTPClient(base_url=base_url, timeout=30)


@click.group(
    epilog="""Examples:

  aitbc governance propose --title 'Increase block reward' --description '...'

  aitbc governance list"""
)
def governance():
    """Create, vote, execute, and inspect OpenClaw DAO governance proposals."""
    pass


@governance.command(
    epilog="""Examples:

  aitbc governance propose --title 'Increase block reward' --description 'Raise reward to 12 AIT'

  aitbc governance propose --title 'Update fee' --description 'Lower tx fee' --category economics"""
)
@click.option("--title", required=True, help="Proposal title")
@click.option("--description", required=True, help="Proposal description")
@click.option(
    "--type", "proposal_type", default="parameter_change", help="Proposal type (parameter_change, fund_allocation, etc.)"
)
@click.option("--category", default="general", help="Proposal category")
@click.option("--proposer-id", required=True, help="Proposer profile ID")
@click.option("--proposer-address", default="", help="Proposer wallet address (for on-chain submission)")
@click.option("--params", default=None, help="JSON-encoded parameters for parameter_change proposals")
@click.option("--voting-days", type=int, default=7, help="Voting period in days")
@click.option("--wallet", "wallet_name", default=None, help="Wallet to sign the on-chain GOVERNANCE_PROPOSE tx (client-signed submission)")
@click.option("--password", default=None, help="Wallet password")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def propose(
    ctx,
    title: str,
    description: str,
    proposal_type: str,
    category: str,
    proposer_id: str,
    proposer_address: str,
    params: str | None,
    voting_days: int,
    wallet_name: str | None,
    password: str | None,
    format: str,
):
    """Create a new governance proposal with title, description, and optional category."""
    from datetime import UTC, datetime, timedelta

    try:
        proposal_value = {}
        if params:
            proposal_value = json.loads(params)

        voting_starts = datetime.now(UTC).isoformat()
        voting_ends = (datetime.now(UTC) + timedelta(days=voting_days)).isoformat()

        client = _get_client(ctx)
        proposal_data = {
            "title": title,
            "description": description,
            "proposal_type": proposal_type,
            "category": category,
            "proposer_id": proposer_id,
            "proposer_address": proposer_address,
            "proposal_value": proposal_value,
            "voting_starts": voting_starts,
            "voting_ends": voting_ends,
        }
        signer = _wallet_signer(ctx, wallet_name, password)
        if signer:
            signer_address, private_key = signer
            if proposer_address and proposer_address.lower() != signer_address.lower():
                raise click.ClickException("--proposer-address does not match the --wallet address")
            proposer_address = proposer_address or signer_address
            proposal_id = f"prop_{uuid.uuid4().hex[:8]}"
            proposal_data["proposal_id"] = proposal_id
            proposal_data["proposer_address"] = proposer_address
            http_client, chain_id = _governance_rpc(ctx)
            proposal_data["chain_id"] = chain_id
            try:
                height = int(http_client.get(f"/rpc/height?chain_id={chain_id}").get("height", 0))
            except Exception:
                height = 0
            # ~2s block time → ~43200 blocks/day; matches the service's
            # voting_period_blocks convention.
            blocks_per_day = 43200
            proposal_data["signed_tx"] = _sign_governance_tx(
                http_client,
                chain_id,
                private_key,
                signer_address,
                "GOVERNANCE_PROPOSE",
                {
                    "proposal_id": proposal_id,
                    "proposer": proposer_address,
                    "title": title,
                    "description": description,
                    "proposal_type": proposal_type,
                    "parameters": proposal_value,
                    "voting_starts_block": height,
                    "voting_ends_block": height + voting_days * blocks_per_day,
                },
            )
        result = client.post("/v1/governance/proposals", json=proposal_data)
        output(result, ctx.obj.get("output_format", format))
    except json.JSONDecodeError:
        error("Invalid JSON in --params")
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error creating proposal: {e}")


@governance.command(
    epilog="""Examples:

  aitbc governance vote --proposal-id prop-123 --vote for

  aitbc governance vote --proposal-id prop-123 --vote against --voting-power 100"""
)
@click.option("--proposal-id", required=True, help="Proposal ID to vote on")
@click.option("--voter-id", required=True, help="Voter profile ID")
@click.option("--vote", type=click.Choice(["for", "against", "abstain"]), required=True, help="Vote choice")
@click.option("--voter-address", default="", help="Voter wallet address (for on-chain voting power)")
@click.option("--reason", default="", help="Reason for the vote")
@click.option(
    "--voting-power", type=float, default=0.0, help="Voting power (auto-calculated from on-chain balance if enabled)"
)
@click.option("--wallet", "wallet_name", default=None, help="Wallet to sign the on-chain GOVERNANCE_VOTE tx (client-signed submission)")
@click.option("--password", default=None, help="Wallet password")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def vote(
    ctx,
    proposal_id: str,
    voter_id: str,
    vote: str,
    voter_address: str,
    reason: str,
    voting_power: float,
    wallet_name: str | None,
    password: str | None,
    format: str,
):
    """Vote for, against, or abstain on a governance proposal."""
    try:
        client = _get_client(ctx)
        vote_data = {
            "proposal_id": proposal_id,
            "voter_id": voter_id,
            "voter_address": voter_address,
            "vote_type": vote,
            "voting_power": voting_power,
            "reason": reason,
        }
        signer = _wallet_signer(ctx, wallet_name, password)
        if signer:
            signer_address, private_key = signer
            if voter_address and voter_address.lower() != signer_address.lower():
                raise click.ClickException("--voter-address does not match the --wallet address")
            voter_address = voter_address or signer_address
            vote_data["voter_address"] = voter_address
            from aitbc.crypto.signature_recovery import canonical_address

            http_client, chain_id = _governance_rpc(ctx)
            vote_data["chain_id"] = chain_id
            account = _get_governance_account(http_client, canonical_address(voter_address), chain_id)
            onchain_power = account.get("balance", 0) or 0
            vote_data["signed_tx"] = _sign_governance_tx(
                http_client,
                chain_id,
                private_key,
                signer_address,
                "GOVERNANCE_VOTE",
                {
                    "proposal_id": proposal_id,
                    "voter": voter_address,
                    "vote_type": vote,
                    # The on-chain record must carry the real balance snapshot —
                    # the service verifies it against a fresh query.
                    "voting_power": onchain_power,
                    "reason": reason,
                },
                account=account,
            )
        result = client.post("/v1/governance/votes", json=vote_data)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error casting vote: {e}")


@governance.command(
    epilog="""Examples:

  aitbc governance list

  aitbc governance list --status active --category economics"""
)
@click.option("--status", default=None, help="Filter by status (draft, active, succeeded, defeated, executed, cancelled)")
@click.option("--category", default=None, help="Filter by category")
@click.option("--proposer-id", default=None, help="Filter by proposer ID")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list(ctx, status: str | None, category: str | None, proposer_id: str | None, format: str):
    """List governance proposals with optional status, category, and proposer filters."""
    try:
        client = _get_client(ctx)
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        if proposer_id:
            params["proposer_id"] = proposer_id
        result = client.get("/v1/governance/proposals", params=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error listing proposals: {e}")


@governance.command(
    epilog="""Examples:

  aitbc governance execute --proposal-id prop-123

  aitbc governance execute --proposal-id prop-123 --executor-address 0x..."""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--executor-address", default="", help="Executor wallet address (for on-chain execution)")
@click.option("--wallet", "wallet_name", default=None, help="Wallet to sign the on-chain GOVERNANCE_EXECUTE tx (client-signed submission)")
@click.option("--password", default=None, help="Wallet password")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def execute(ctx, proposal_id: str, executor_address: str, wallet_name: str | None, password: str | None, format: str):
    """Execute an approved governance proposal on-chain."""
    try:
        client = _get_client(ctx)
        query = ""
        body: dict | None = None
        signer = _wallet_signer(ctx, wallet_name, password)
        if signer:
            signer_address, private_key = signer
            if executor_address and executor_address.lower() != signer_address.lower():
                raise click.ClickException("--executor-address does not match the --wallet address")
            executor_address = executor_address or signer_address
            http_client, chain_id = _governance_rpc(ctx)
            body = {
                "signed_tx": _sign_governance_tx(
                    http_client,
                    chain_id,
                    private_key,
                    signer_address,
                    "GOVERNANCE_EXECUTE",
                    {"proposal_id": proposal_id, "executor": executor_address},
                )
            }
        if executor_address:
            query = f"?executor_address={executor_address}"
        result = client.post(f"/v1/governance/proposals/{proposal_id}/execute{query}", json=body)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error executing proposal: {e}")


@governance.command(
    epilog="""Examples:

  aitbc governance close --proposal-id prop-123

  aitbc governance close --proposal-id prop-123 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def close(ctx, proposal_id: str, format: str):
    """Close a governance proposal and tally the final votes."""
    try:
        client = _get_client(ctx)
        result = client.post(f"/v1/governance/proposals/{proposal_id}/close")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error closing proposal: {e}")


@governance.command(
    epilog="""Examples:

  aitbc governance status

  aitbc governance status --output json"""
)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status(ctx, format: str):
    """Show the global status of the governance system."""
    try:
        client = _get_client(ctx)
        result = client.get("/v1/governance/status")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting governance status: {e}")


@governance.command(
    epilog="""Examples:

  aitbc governance get --proposal-id prop-123

  aitbc governance get --proposal-id prop-123 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def get(ctx, proposal_id: str, format: str):
    """Get details of a specific governance proposal."""
    try:
        client = _get_client(ctx)
        result = client.get(f"/v1/governance/proposals/{proposal_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting proposal: {e}")


# ============================================================================
# v0.7.4 §B8: Cross-chain governance CLI commands
# ============================================================================


@governance.command(
    epilog="""Examples:

  aitbc governance propagate --proposal-id prop-123 --target-chains ait-side-1,ait-side-2

  aitbc governance propagate --proposal-id prop-123 --target-chains ait-side-1"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--target-chains", required=True, help="Comma-separated list of target chain IDs")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def propagate(ctx, proposal_id: str, target_chains: str, format: str):
    """Propagate a governance proposal to a comma-separated list of target chains."""
    try:
        chains = [c.strip() for c in target_chains.split(",") if c.strip()]
        if not chains:
            error("--target-chains must specify at least one chain ID")
            return
        client = _get_client(ctx)
        result = client.post(
            f"/v1/governance/proposals/{proposal_id}/propagate",
            json={"target_chains": chains},
        )
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error propagating proposal: {e}")


@governance.command(
    name="aggregate-votes",
    epilog="""Examples:

  aitbc governance aggregate-votes --proposal-id prop-123

  aitbc governance aggregate-votes --proposal-id prop-123 --output json""",
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def aggregate_votes(ctx, proposal_id: str, format: str):
    """Aggregate and tally cross-chain votes for a proposal."""
    try:
        client = _get_client(ctx)
        result = client.post(f"/v1/governance/proposals/{proposal_id}/aggregate-votes")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error aggregating votes: {e}")


@governance.command(
    name="execute-cross-chain",
    epilog="""Examples:

  aitbc governance execute-cross-chain --proposal-id prop-123

  aitbc governance execute-cross-chain --proposal-id prop-123 --output json""",
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def execute_cross_chain(ctx, proposal_id: str, format: str):
    """Execute a governance proposal across target chains."""
    try:
        client = _get_client(ctx)
        result = client.post(f"/v1/governance/proposals/{proposal_id}/execute-cross-chain")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error executing cross-chain: {e}")


__all__ = ["governance"]
