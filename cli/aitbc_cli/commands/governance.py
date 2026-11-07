"""Governance CLI commands (v0.7.3).

Provides commands for on-chain governance operations:
- ``governance propose`` — create a governance proposal
- ``governance vote`` — cast an advisory vote on a proposal (V-7)
- ``governance list`` — list proposals (with optional status filter)
- ``governance execute`` — execute a passed proposal after timelock
- ``governance status`` — get governance service status
- ``governance get`` — get a specific proposal by ID

These commands talk to the governance service REST API (port 8105)
rather than non-existent blockchain RPC endpoints. The governance
service handles on-chain tx submission when ``enable_onchain_submission``
is enabled in its config.
"""

import builtins
import json
import time
import uuid
from typing import Any

import click

from ..config import get_config
from ..utils import output, resolve_output_format
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError
from ..utils.wallet_secret import wallet_password_options

GOVERNANCE_SERVICE_URL = "http://localhost:8105"


def _governance_rpc(ctx: click.Context) -> tuple[AITBCHTTPClient, str]:
    """Return an RPC client for the node's transaction endpoint + chain_id."""
    from aitbc_cli.commands.wallet.staking import _get_chain_id, _get_rpc_url

    rpc_url = _get_rpc_url(ctx)
    return AITBCHTTPClient(base_url=rpc_url, timeout=10), _get_chain_id(ctx, rpc_url)


def _get_governance_account(http_client: AITBCHTTPClient, address: str, chain_id: str) -> dict:
    """Fetch the on-chain account (nonce + balance) for the signing address."""
    try:
        return http_client.get(f"/rpc/account/{address}?chain_id={chain_id}")
    except Exception:
        return {}


def _get_sealed_execution_payload(http_client: AITBCHTTPClient, proposal_id: str, chain_id: str) -> dict:
    """Fetch the ``execution_payload`` a proposal's GOVERNANCE_PROPOSE sealed (#1214).

    The v13 chain binding requires GOVERNANCE_EXECUTE's ``payload.execution_payload``
    to equal the dict committed at propose time; signing without it produces a tx
    the node always rejects. Refuses rather than signs an unbindable EXECUTE.
    """
    try:
        sealed = http_client.get(f"/rpc/governance/sealed-proposal/{proposal_id}", params={"chain_id": chain_id})
    except Exception as e:
        raise click.ClickException(f"cannot fetch sealed proposal {proposal_id}: {e}") from e
    payload = sealed.get("execution_payload")
    if not isinstance(payload, dict):
        inner = (sealed.get("payload") or {}).get("execution_payload")
        payload = inner if isinstance(inner, dict) else None
    if payload is None:
        raise click.ClickException(
            f"proposal {proposal_id} has no sealed execution_payload on {chain_id} — "
            "an EXECUTE without it is rejected by the v13 binding"
        )
    return payload


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


def _wallet_signer(
    ctx: click.Context,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None = None,
    password_stdin: bool = False,
) -> tuple[str, str] | None:
    """Resolve the signing wallet when --wallet/AITBC_DEFAULT_WALLET is set."""
    from ..utils.agent_signing import load_signing_wallet

    try:
        return load_signing_wallet(ctx, wallet_name, password, password_file=password_file, password_stdin=password_stdin)
    except Exception as e:
        raise click.ClickException(str(e)) from e


def _sign_body(private_key: str, payload: dict) -> str:
    """secp256k1 signature over the canonical JSON of ``payload``.

    Matches the governance service's write-route check (#1091): keccak256 of
    the sorted compact JSON encoding, signed by the caller's wallet. Used so
    the CLI's signed write bodies pass the route gate (#1131).
    """
    import json as _json

    from eth_keys import keys
    from eth_utils import keccak

    msg = _json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(str(private_key).removeprefix("0x")))
    return pk.sign_msg_hash(keccak(msg)).to_hex()


def _governance_voting_period_blocks(client: AITBCHTTPClient, proposal_type: str) -> int:
    """Return the service's live voting window in blocks (#770).

    The sealed ``GOVERNANCE_PROPOSE`` payload and the service's stored
    ``voting_ends_block`` must describe the same window, so the value comes
    from ``/v1/governance/status`` — never from an assumed block cadence.
    There is deliberately no fallback: a propose that cannot read the
    service's window is refused rather than sealing a guessed one.
    """
    key = "emergency_voting_period_blocks" if proposal_type == "emergency" else "voting_period_blocks"
    try:
        status = client.get("/v1/governance/status")
    except Exception as e:
        raise click.ClickException(f"cannot read the governance voting window from /v1/governance/status: {e}") from e
    value = status.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise click.ClickException(
            f"governance service did not report a usable {key} ({value!r}); refusing to seal a guessed voting window"
        )
    return value


def _proposal_request_body(
    *,
    title: str,
    description: str,
    proposal_type: str,
    category: str,
    proposer_id: str,
    proposer_address: str,
    proposal_value: dict,
    voting_days: int | None,
) -> dict:
    """Assemble the ``/v1/governance/proposals`` request body.

    The wall-clock window is only sent as an explicit ``--voting-days``
    override; by default the service derives ``voting_ends`` from the same
    ``voting_period_blocks`` that bound the sealed block window (#770).
    """
    from datetime import UTC, datetime, timedelta

    body = {
        "title": title,
        "description": description,
        "proposal_type": proposal_type,
        "category": category,
        "proposer_id": proposer_id,
        "proposer_address": proposer_address,
        "proposal_value": proposal_value,
        "voting_starts": datetime.now(UTC).isoformat(),
    }
    if voting_days is not None:
        body["voting_ends"] = (datetime.now(UTC) + timedelta(days=voting_days)).isoformat()
    return body


def _prepare_signed_proposal(
    ctx: click.Context,
    signer_address: str,
    private_key: str,
    proposer_address: str,
    proposal_data: dict,
    tx_payload: dict,
    voting_period_blocks: int,
) -> None:
    """Bind the proposer to the signer and attach the client-signed
    GOVERNANCE_PROPOSE tx to ``proposal_data`` in place."""
    if proposer_address and proposer_address.lower() != signer_address.lower():
        raise click.ClickException("--proposer-address does not match the --wallet address")
    proposer_address = proposer_address or signer_address
    proposal_data["proposal_id"] = f"prop_{uuid.uuid4().hex[:8]}"
    proposal_data["proposer_address"] = proposer_address
    # Route gate (#1091): proposer_id must equal the signing address;
    # the service binds and stores it.
    proposal_data["proposer_id"] = proposer_address
    http_client, chain_id = _governance_rpc(ctx)
    proposal_data["chain_id"] = chain_id
    try:
        height = int(http_client.get(f"/rpc/height?chain_id={chain_id}").get("height", 0))
    except Exception:
        height = 0
    # The sealed window is the service's own voting_period_blocks (#770) —
    # the service re-derives and stores the same value, so the payload can
    # never disagree with what the service enforces.
    tx_payload.update(
        {
            "proposal_id": proposal_data["proposal_id"],
            "proposer": proposer_address,
            "voting_starts_block": height,
            "voting_ends_block": height + voting_period_blocks,
        }
    )
    proposal_data["signed_tx"] = _sign_governance_tx(
        http_client, chain_id, private_key, signer_address, "GOVERNANCE_PROPOSE", tx_payload
    )


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
@click.option(
    "--proposer-id", required=True, help="Proposer profile ID (with --wallet the signed value is the wallet address)"
)
@click.option("--proposer-address", default="", help="Proposer wallet address (for on-chain submission)")
@click.option("--params", default=None, help="JSON-encoded parameters for parameter_change proposals")
@click.option(
    "--execution-payload",
    default=None,
    help="JSON the EXECUTE binds to (v13). Defaults to --params; required for any non-parameter_change proposal",
)
@click.option(
    "--voting-days",
    type=int,
    default=None,
    help="Wall-clock voting window override in days; the sealed block window always uses the service's voting_period_blocks",
)
@click.option(
    "--wallet",
    "wallet_name",
    default=None,
    help="Wallet to sign the on-chain GOVERNANCE_PROPOSE tx (client-signed submission)",
)
@wallet_password_options
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
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
    execution_payload: str | None,
    voting_days: int,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    format: str,
):
    """Create a new governance proposal with title, description, and optional category."""
    try:
        proposal_value = {}
        if params:
            proposal_value = json.loads(params)
        execution_payload_value = proposal_value
        if execution_payload:
            execution_payload_value = json.loads(execution_payload)
            if not isinstance(execution_payload_value, dict):
                abort(ctx, "--execution-payload must be a JSON object")

        client = _get_client(ctx)
        proposal_data = _proposal_request_body(
            title=title,
            description=description,
            proposal_type=proposal_type,
            category=category,
            proposer_id=proposer_id,
            proposer_address=proposer_address,
            proposal_value=proposal_value,
            voting_days=voting_days,
        )
        signer = _wallet_signer(ctx, wallet_name, password, password_file=password_file, password_stdin=password_stdin)
        if signer:
            signer_address, private_key = signer
            # v13 binds GOVERNANCE_EXECUTE to the sealed execution_payload — a
            # missing field 400s every propose. The params JSON is the execution
            # intent unless --execution-payload overrides it.
            _prepare_signed_proposal(
                ctx,
                signer_address,
                private_key,
                proposer_address,
                proposal_data,
                {
                    "title": title,
                    "description": description,
                    "proposal_type": proposal_type,
                    "parameters": proposal_value,
                    "execution_payload": execution_payload_value,
                },
                _governance_voting_period_blocks(client, proposal_type),
            )
        if signer:
            proposal_data["signature"] = _sign_body(private_key, {k: v for k, v in proposal_data.items() if k != "signature"})
        result = client.post("/v1/governance/proposals", json=proposal_data)
        output(result, resolve_output_format(ctx, format))
    except json.JSONDecodeError:
        abort(ctx, "Invalid JSON in --params")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except click.ClickException:
        raise
    except Exception as e:
        abort(ctx, f"Error creating proposal: {e}", from_exception=e)


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
@click.option(
    "--wallet", "wallet_name", default=None, help="Wallet to sign the on-chain GOVERNANCE_VOTE tx (client-signed submission)"
)
@wallet_password_options
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
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
    password_file: str | None,
    password_stdin: bool,
    format: str,
):
    """Vote for, against, or abstain on a governance proposal. Votes are advisory (V-7) — the tally informs but does not decide execution; GOVERNANCE_EXECUTE is gated only by the governance_executors chain parameter."""
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
        signer = _wallet_signer(ctx, wallet_name, password, password_file=password_file, password_stdin=password_stdin)
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
        if signer:
            vote_data["voter_id"] = voter_address
            vote_data["signature"] = _sign_body(private_key, {k: v for k, v in vote_data.items() if k != "signature"})
        result = client.post("/v1/governance/votes", json=vote_data)
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error casting vote: {e}", from_exception=e)


@governance.command(
    epilog="""Examples:

  aitbc governance list

  aitbc governance list --status active --category economics"""
)
@click.option("--status", default=None, help="Filter by status (draft, active, succeeded, defeated, executed, cancelled)")
@click.option("--category", default=None, help="Filter by category")
@click.option("--proposer-id", default=None, help="Filter by proposer ID")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
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
        # GET /v1/governance/proposals returns a bare JSON array; get()
        # narrows via expect_object and raises TypeError on non-object
        # bodies (#552).
        result = client.get_json("/v1/governance/proposals", params=params)
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing proposals: {e}", from_exception=e)


@governance.command(
    epilog="""Examples:

  aitbc governance execute --proposal-id prop-123

  aitbc governance execute --proposal-id prop-123 --executor-address 0x..."""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--executor-address", default="", help="Executor wallet address (for on-chain execution)")
@click.option(
    "--wallet",
    "wallet_name",
    default=None,
    help="Wallet to sign the on-chain GOVERNANCE_EXECUTE tx (client-signed submission)",
)
@wallet_password_options
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def execute(
    ctx,
    proposal_id: str,
    executor_address: str,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    format: str,
):
    """Execute a governance proposal on-chain as a governance executor (the vote tally is advisory and does not decide execution; V-7)."""
    try:
        client = _get_client(ctx)
        query = ""
        body: dict | None = None
        signer = _wallet_signer(ctx, wallet_name, password, password_file=password_file, password_stdin=password_stdin)
        if signer:
            signer_address, private_key = signer
            if executor_address and executor_address.lower() != signer_address.lower():
                raise click.ClickException("--executor-address does not match the --wallet address")
            executor_address = executor_address or signer_address
            http_client, chain_id = _governance_rpc(ctx)
            execute_fields: dict = {"proposal_id": proposal_id, "executor": executor_address}
            # v13: EXECUTE must carry the execution_payload sealed at PROPOSE (#1214).
            execute_fields["execution_payload"] = _get_sealed_execution_payload(http_client, proposal_id, chain_id)
            body = {
                "signed_tx": _sign_governance_tx(
                    http_client,
                    chain_id,
                    private_key,
                    signer_address,
                    "GOVERNANCE_EXECUTE",
                    execute_fields,
                )
            }
        if executor_address:
            query = f"?executor_address={executor_address}"
        if signer:
            body = body or {}
            body["caller_address"] = executor_address
            body["signature"] = _sign_body(private_key, {"action": "execute", "proposal_id": proposal_id})
        result = client.post(f"/v1/governance/proposals/{proposal_id}/execute{query}", json=body)
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error executing proposal: {e}", from_exception=e)


@governance.command(
    epilog="""Examples:

  aitbc governance close --proposal-id prop-123

  aitbc governance close --proposal-id prop-123 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--wallet", "wallet_name", default=None, help="Wallet to sign the close request (required by the service)")
@wallet_password_options
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def close(
    ctx,
    proposal_id: str,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    format: str,
):
    """Close a governance proposal and tally the final votes."""
    try:
        client = _get_client(ctx)
        body: dict | None = None
        signer = _wallet_signer(ctx, wallet_name, password, password_file=password_file, password_stdin=password_stdin)
        if signer:
            signer_address, private_key = signer
            body = {
                "caller_address": signer_address,
                "signature": _sign_body(private_key, {"action": "close", "proposal_id": proposal_id}),
            }
        result = client.post(f"/v1/governance/proposals/{proposal_id}/close", json=body)
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error closing proposal: {e}", from_exception=e)


@governance.command(
    epilog="""Examples:

  aitbc governance status

  aitbc governance status --output json"""
)
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def status(ctx, format: str):
    """Show the global status of the governance system."""
    try:
        client = _get_client(ctx)
        result = client.get("/v1/governance/status")
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting governance status: {e}", from_exception=e)


@governance.command(
    epilog="""Examples:

  aitbc governance get --proposal-id prop-123

  aitbc governance get --proposal-id prop-123 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def get(ctx, proposal_id: str, format: str):
    """Get details of a specific governance proposal."""
    try:
        client = _get_client(ctx)
        # The governance service answers an object for this route, but has
        # also been observed returning a JSON array of proposals — accept
        # both shapes and pick the one matching the requested id.
        payload = client.get_json(f"/v1/governance/proposals/{proposal_id}")
        result: dict[str, Any] | None = payload if isinstance(payload, dict) else None
        if result is None and isinstance(payload, builtins.list):
            candidates: builtins.list[Any] = payload
            for p in candidates:
                if isinstance(p, dict) and p.get("proposal_id") == proposal_id:
                    result = p
                    break
        if result is None:
            abort(ctx, f"Proposal {proposal_id} not found")
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting proposal: {e}", from_exception=e)


@governance.group(
    epilog="""Examples:

  aitbc governance proposal show --proposal-id prop-123"""
)
def proposal():
    """Inspect a proposal's sealed on-chain record."""
    pass


@proposal.command(
    name="show",
    epilog="""Examples:

  aitbc governance proposal show --proposal-id prop-123

  aitbc governance proposal show --proposal-id prop-123 --output json""",
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def proposal_show(ctx, proposal_id: str, format: str):
    """Show the sealed GOVERNANCE_PROPOSE record for a proposal id.

    Reads the canonical transaction table on the node's blockchain RPC — the
    same source the v13 EXECUTE precheck binds to — and returns the sealed
    payload including ``execution_payload``, plus whether an EXECUTE already
    sealed. ``governance get`` reads the governance *service* view instead;
    this command answers what the chain itself committed (GAP-PROPOSAL-SHOW-1).
    """
    try:
        client, chain_id = _governance_rpc(ctx)
        result = client.get(f"/rpc/governance/sealed-proposal/{proposal_id}", params={"chain_id": chain_id})
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting sealed proposal: {e}", from_exception=e)


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
@click.option(
    "--wallet",
    "wallet_name",
    default=None,
    help="Wallet that signs the call — must be the proposal's proposer_address (service-enforced, #1178)",
)
@wallet_password_options
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def propagate(
    ctx,
    proposal_id: str,
    target_chains: str,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    format: str,
):
    """Propagate a governance proposal to a comma-separated list of target chains."""
    try:
        chains = [c.strip() for c in target_chains.split(",") if c.strip()]
        if not chains:
            abort(ctx, "--target-chains must specify at least one chain ID")
            return
        client = _get_client(ctx)
        body: dict[str, Any] = {"target_chains": chains}
        signer = _wallet_signer(ctx, wallet_name, password, password_file=password_file, password_stdin=password_stdin)
        if signer:
            signer_address, private_key = signer
            body["caller_address"] = signer_address
            body["timestamp"] = time.time()
            body["signature"] = _sign_body(private_key, {k: v for k, v in body.items() if k != "signature"})
        result = client.post(
            f"/v1/governance/proposals/{proposal_id}/propagate",
            json=body,
        )
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error propagating proposal: {e}", from_exception=e)


@governance.command(
    name="aggregate-votes",
    epilog="""Examples:

  aitbc governance aggregate-votes --proposal-id prop-123

  aitbc governance aggregate-votes --proposal-id prop-123 --output json""",
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option(
    "--wallet",
    "wallet_name",
    default=None,
    help="Wallet that signs the call (service-enforced caller signature, #1178)",
)
@wallet_password_options
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def aggregate_votes(
    ctx,
    proposal_id: str,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    format: str,
):
    """Aggregate and tally votes for a proposal (informational only — votes are advisory, V-7)."""
    try:
        client = _get_client(ctx)
        body: dict[str, Any] = {}
        signer = _wallet_signer(ctx, wallet_name, password, password_file=password_file, password_stdin=password_stdin)
        if signer:
            signer_address, private_key = signer
            body["caller_address"] = signer_address
            body["timestamp"] = time.time()
            body["signature"] = _sign_body(private_key, {k: v for k, v in body.items() if k != "signature"})
        result = client.post(f"/v1/governance/proposals/{proposal_id}/aggregate-votes", json=body)
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error aggregating votes: {e}", from_exception=e)


@governance.command(
    name="execute-cross-chain",
    epilog="""Examples:

  aitbc governance execute-cross-chain --proposal-id prop-123

  aitbc governance execute-cross-chain --proposal-id prop-123 --output json""",
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option(
    "--wallet",
    "wallet_name",
    default=None,
    help="Wallet that signs the call — must be the proposal's proposer_address (service-enforced, #1178)",
)
@wallet_password_options
@click.option("--format", type=click.Choice(["table", "json"]), default=None, help="Output format")
@click.pass_context
def execute_cross_chain(
    ctx,
    proposal_id: str,
    wallet_name: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    format: str,
):
    """Execute a governance proposal across target chains."""
    try:
        client = _get_client(ctx)
        body: dict[str, Any] = {}
        signer = _wallet_signer(ctx, wallet_name, password, password_file=password_file, password_stdin=password_stdin)
        if signer:
            signer_address, private_key = signer
            body["caller_address"] = signer_address
            body["timestamp"] = time.time()
            body["signature"] = _sign_body(private_key, {k: v for k, v in body.items() if k != "signature"})
        result = client.post(f"/v1/governance/proposals/{proposal_id}/execute-cross-chain", json=body)
        output(result, resolve_output_format(ctx, format))
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error executing cross-chain: {e}", from_exception=e)


__all__ = ["governance"]
