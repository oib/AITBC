"""Mutating AITBC CLI wrapper MCP tools (split from aitbc_mcp_server, #1867)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field


from aitbc_mcp_server import (
    DEFAULT_WALLET_DIR,
    NodeRole,
    _build_aitbc_cli_command,
    _host_for_role,
    _json,
    _require_confirm,
    _run_aitbc_cli,
    mcp,
)

# ---------------------------------------------------------------------------
# Mutating aitbc CLI wrappers
# ---------------------------------------------------------------------------


def _merge_cli_string_options(options: dict[str, str | None], fields: dict[str, str | None]) -> None:
    for cli_key, value in fields.items():
        if value is not None:
            options[cli_key] = value


def _merge_cli_numeric_options(options: dict[str, str | None], fields: dict[str, float | int | Decimal | None]) -> None:
    for cli_key, value in fields.items():
        if value is not None:
            options[cli_key] = str(value)


def _merge_cli_flag_options(options: dict[str, str | None], flags: dict[str, bool]) -> None:
    for cli_key, enabled in flags.items():
        if enabled:
            options[cli_key] = None


def _submit_ai_job_cli_options(
    *,
    prompt: str,
    currency: str,
    wallet: str | None,
    job_type: str | None,
    model: str | None,
    payment: str | None,
    offer_id: str | None,
    min_reputation: float | None,
    buyer_address: str | None,
    provider_address: str | None,
    buyer_agent_id: str | None,
    provider_agent_id: str | None,
    offer_quantity: str | None,
    acceptance_window: int | None,
    zk_proof_required: bool,
    confidential: bool,
    auto_reinvest_pct: float | None,
    bond_required: bool,
    min_bond_amount: Decimal | None,
    wait: bool,
    timeout: int | None,
) -> dict[str, str | None]:
    """Map ``submit_ai_job`` parameters to ``aitbc ai submit`` CLI options."""
    options: dict[str, str | None] = {"prompt": prompt, "currency": currency}
    _merge_cli_string_options(
        options,
        {
            "wallet": wallet,
            "type": job_type,
            "model": model,
            "payment": payment,
            "offer-id": offer_id,
            "buyer-address": buyer_address,
            "provider-address": provider_address,
            "buyer-agent-id": buyer_agent_id,
            "provider-agent-id": provider_agent_id,
            "offer-quantity": offer_quantity,
        },
    )
    _merge_cli_numeric_options(
        options,
        {
            "min-reputation": min_reputation,
            "acceptance-window": acceptance_window,
            "auto-reinvest-pct": auto_reinvest_pct,
            "min-bond-amount": min_bond_amount,
            "timeout": timeout,
        },
    )
    _merge_cli_flag_options(
        options,
        {
            "zk-proof-required": zk_proof_required,
            "confidential": confidential,
            "bond-required": bond_required,
            "wait": wait,
        },
    )
    return options


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def submit_ai_job(
    prompt: Annotated[
        str,
        Field(description="Prompt or input for the AI job."),
    ],
    wallet: Annotated[
        str | None,
        Field(description="Wallet name to pay for the job."),
    ] = None,
    job_type: Annotated[
        str | None,
        Field(description="Job type, e.g. 'ollama', 'whisper', 'ffmpeg'."),
    ] = None,
    model: Annotated[
        str | None,
        Field(description="Ollama model to use (for ollama jobs)."),
    ] = None,
    payment: Annotated[
        str | None,
        Field(description="Payment amount, e.g. '0.1'"),
    ] = None,
    currency: Annotated[
        str,
        Field(description="Payment currency."),
    ] = "AITBC",
    offer_id: Annotated[
        str | None,
        Field(description="Market offer ID this job is bought against."),
    ] = None,
    min_reputation: Annotated[
        float | None,
        Field(description="Minimum provider reputation (0-1).", ge=0, le=1),
    ] = None,
    buyer_address: Annotated[
        str | None,
        Field(description="Customer wallet address for escrow."),
    ] = None,
    provider_address: Annotated[
        str | None,
        Field(description="Provider wallet address for escrow."),
    ] = None,
    buyer_agent_id: Annotated[
        str | None,
        Field(description="Buyer agent id; payment address resolved via coordinator."),
    ] = None,
    provider_agent_id: Annotated[
        str | None,
        Field(description="Provider agent id; payment address resolved via coordinator."),
    ] = None,
    offer_quantity: Annotated[
        str | None,
        Field(description="How many of the offer's price units to buy."),
    ] = None,
    acceptance_window: Annotated[
        int | None,
        Field(description="Seconds after completion before payment auto-releases.", ge=0),
    ] = None,
    zk_proof_required: Annotated[
        bool,
        Field(description="Require a ZK receipt proof before escrow release."),
    ] = False,
    confidential: Annotated[
        bool,
        Field(description="Mark this job as confidential."),
    ] = False,
    auto_reinvest_pct: Annotated[
        float | None,
        Field(description="Percentage of released payment to auto-stake as reinvestment.", ge=0, le=100),
    ] = None,
    bond_required: Annotated[
        bool,
        Field(description="Require the provider to have an active performance bond."),
    ] = False,
    min_bond_amount: Annotated[
        Decimal | None,
        Field(description="Minimum bond amount required for provider eligibility.", ge=Decimal("0")),
    ] = None,
    wait: Annotated[
        bool,
        Field(description="Wait for the job to reach a terminal state."),
    ] = False,
    timeout: Annotated[
        int | None,
        Field(
            description=(
                "Seconds to wait when --wait is used (max 600). The remote CLI run gets "
                "timeout+30s of subprocess budget so the wait is not cut off early "
                "(V13-RES2-MCP-WAIT-1, #1715)."
            ),
            ge=1,
            le=600,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Submit an AI job via the aitbc CLI."""
    options = _submit_ai_job_cli_options(
        prompt=prompt,
        currency=currency,
        wallet=wallet,
        job_type=job_type,
        model=model,
        payment=payment,
        offer_id=offer_id,
        min_reputation=min_reputation,
        buyer_address=buyer_address,
        provider_address=provider_address,
        buyer_agent_id=buyer_agent_id,
        provider_agent_id=provider_agent_id,
        offer_quantity=offer_quantity,
        acceptance_window=acceptance_window,
        zk_proof_required=zk_proof_required,
        confidential=confidential,
        auto_reinvest_pct=auto_reinvest_pct,
        bond_required=bond_required,
        min_bond_amount=min_bond_amount,
        wait=wait,
        timeout=timeout,
    )

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("ai", "submit", None, options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    # The remote subprocess budget must cover the --wait window plus submit
    # overhead, or a large --timeout silently truncates to timed_out at the
    # _run_aitbc_cli default of 120s (#1715).
    subprocess_timeout = timeout + 30 if (wait and timeout is not None) else 120
    return _json(_run_aitbc_cli(target, "ai", "submit", None, options, "json", timeout=subprocess_timeout))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def pay_for_ai_job(
    job_id: Annotated[
        str,
        Field(description="Job ID to pay for."),
    ],
    wallet: Annotated[
        str,
        Field(description="Wallet name to sign the escrow lock."),
    ],
    buyer_address: Annotated[
        str | None,
        Field(description="Override buyer/customer address."),
    ] = None,
    provider_address: Annotated[
        str | None,
        Field(description="Override provider address."),
    ] = None,
    buyer_agent_id: Annotated[
        str | None,
        Field(description="Buyer agent id; payment address resolved via coordinator."),
    ] = None,
    provider_agent_id: Annotated[
        str | None,
        Field(description="Provider agent id; payment address resolved via coordinator."),
    ] = None,
    currency: Annotated[
        str,
        Field(description="Payment currency."),
    ] = "AITBC",
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create an escrow payment for an existing job (two-step payment flow)."""
    options: dict[str, str | None] = {"job-id": job_id, "wallet": wallet, "currency": currency}
    if buyer_address is not None:
        options["buyer-address"] = buyer_address
    if provider_address is not None:
        options["provider-address"] = provider_address
    if buyer_agent_id is not None:
        options["buyer-agent-id"] = buyer_agent_id
    if provider_agent_id is not None:
        options["provider-agent-id"] = provider_agent_id

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("ai", "pay", None, options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "ai", "pay", None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def manage_ai_job(
    action: Annotated[
        Literal["accept", "cancel", "refund"],
        Field(description="Action to perform: accept a completed job, cancel a queued job, or refund a job."),
    ],
    job_id: Annotated[
        str,
        Field(description="Job ID to manage."),
    ],
    wallet: Annotated[
        str | None,
        Field(description="Wallet name (only used for cancel)."),
    ] = None,
    refund: Annotated[
        bool,
        Field(description="For cancel, also refund the escrowed payment."),
    ] = False,
    reason: Annotated[
        str,
        Field(description="Reason for cancel or refund."),
    ] = "buyer_requested",
    coordinator_url: Annotated[
        str | None,
        Field(description="Override coordinator URL."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Accept, cancel or refund an AI job through the aitbc CLI."""
    options: dict[str, str | None] = {"job-id": job_id}
    if action == "cancel" and wallet is not None:
        options["wallet"] = wallet
    if action == "cancel" and refund:
        options["refund"] = None
    if action in {"cancel", "refund"}:
        options["reason"] = reason
    if coordinator_url is not None:
        options["coordinator-url"] = coordinator_url

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("ai", action, None, options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "ai", action, None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_zk_refund_sweep_candidates(
    limit: Annotated[
        int,
        Field(description="Maximum completed jobs to inspect.", ge=1),
    ] = 100,
    reason: Annotated[
        str,
        Field(description="Refund reason used for reporting."),
    ] = "buyer_requested",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List completed jobs that the ZK refund sweep would refund (dry run)."""
    options: dict[str, str | None] = {"dry-run": None, "limit": str(limit), "reason": reason}
    target = _host_for_role(role, host)
    return _json(_run_aitbc_cli(target, "ai", "refund-sweep", None, options, "json", timeout=120))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def run_zk_refund_sweep(
    limit: Annotated[
        int,
        Field(description="Maximum completed jobs to inspect.", ge=1),
    ] = 100,
    reason: Annotated[
        str,
        Field(description="Refund reason."),
    ] = "buyer_requested",
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Run the client-side ZK refund sweep for failed ZK escrows."""
    options: dict[str, str | None] = {"limit": str(limit), "reason": reason}
    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("ai", "refund-sweep", None, options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "ai", "refund-sweep", None, options, "json", timeout=120))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def send_aitbc_transaction(
    from_wallet: Annotated[
        str,
        Field(description="Source wallet name."),
    ],
    to_address: Annotated[
        str,
        Field(description="Destination address."),
    ],
    amount: Annotated[
        str,
        Field(description="Amount to send, e.g. '1.5'"),
    ],
    fee: Annotated[
        str | None,
        Field(description="Transaction fee."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Send AITBC from one wallet to another address."""
    options: dict[str, str | None] = {
        "from": from_wallet,
        "to": to_address,
        "amount": amount,
    }
    if fee is not None:
        options["fee"] = fee

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("transactions", "send", None, options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "transactions", "send", None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def send_aitbc_from_env_key(
    key_env: Annotated[
        str,
        Field(
            description=(
                "Name of the environment variable holding the sender's private key "
                "(e.g. 'FAUCET_PRIVATE_KEY'). Only the variable NAME is sent — never "
                "key material. The variable must be set in the environment the aitbc "
                "CLI runs in on the target host (e.g. source the service env file first)."
            )
        ),
    ],
    to_address: Annotated[
        str,
        Field(description="Destination address."),
    ],
    amount: Annotated[
        str,
        Field(description="Amount to send, e.g. '1.5'"),
    ],
    fee: Annotated[
        str | None,
        Field(description="Transaction fee."),
    ] = None,
    rpc_url: Annotated[
        str | None,
        Field(description="Blockchain RPC URL."),
    ] = None,
    nonce_offset: Annotated[
        int | None,
        Field(description="Extra nonce offset for queueing a second pending tx from the same sender."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Send AITBC signed by an env-held private key (no wallet-service entry).

    Wraps ``aitbc transactions send --key-env <NAME> --yes``: the env var must
    already be exported in the remote shell environment (service env files are
    not loaded automatically — e.g. ``set -a; . /etc/aitbc/aitbc-agent-coordinator.env; set +a``
    on the target host). Env-key sends bypass the wallet password flow, so this
    tool is destructive-gated like the other send tools and always passes
    ``--yes`` once ``confirm=true`` — the CLI's own interactive prompt is the
    gate for direct human use.
    """
    options: dict[str, str | None] = {
        "key-env": key_env,
        "to": to_address,
        "amount": amount,
        "yes": None,
    }
    if fee is not None:
        options["fee"] = fee
    if rpc_url is not None:
        options["rpc-url"] = rpc_url
    if nonce_offset is not None:
        options["nonce-offset"] = str(nonce_offset)

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("transactions", "send", None, options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "transactions", "send", None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def create_performance_bond(
    provider_id: Annotated[
        str,
        Field(description="Provider ID or address."),
    ],
    amount: Annotated[
        str,
        Field(description="Amount to lock as a performance bond."),
    ],
    required_amount: Annotated[
        str | None,
        Field(description="Required bond amount for this provider."),
    ] = None,
    bond_id: Annotated[
        str | None,
        Field(description="Optional external bond identifier."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create or top up a provider's performance bond."""
    options: dict[str, str | None] = {"amount": amount}
    if required_amount is not None:
        options["required-amount"] = required_amount
    if bond_id is not None:
        options["bond-id"] = bond_id

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("bond", "create", [provider_id], options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "bond", "create", [provider_id], options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def stake_aitbc(
    amount: Annotated[
        str,
        Field(description="Amount to stake."),
    ],
    wallet_name: Annotated[
        str | None,
        Field(description="Wallet name to stake from."),
    ] = None,
    duration_days: Annotated[
        int | None,
        Field(description="Staking duration in days.", ge=1),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Stake AITBC tokens on the blockchain."""
    group_options: dict[str, str | None] = {}
    if wallet_name is not None:
        group_options["wallet-name"] = wallet_name
    subcommand_options: dict[str, str | None] = {"amount": amount}
    if duration_days is not None:
        subcommand_options["duration"] = str(duration_days)
    env = {"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR}

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command(
        "wallet",
        "stake",
        None,
        group_options=group_options,
        subcommand_options=subcommand_options,
        env=env,
    )
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(
        _run_aitbc_cli(
            target,
            "wallet",
            "stake",
            None,
            None,
            "json",
            group_options=group_options,
            subcommand_options=subcommand_options,
            env=env,
        )
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def unstake_aitbc(
    stake_id: Annotated[
        str,
        Field(description="Stake ID to unstake."),
    ],
    wallet_name: Annotated[
        str | None,
        Field(description="Wallet name to unstake from."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Unstake AITBC tokens from the blockchain."""
    group_options: dict[str, str | None] = {}
    if wallet_name is not None:
        group_options["wallet-name"] = wallet_name
    subcommand_options: dict[str, str | None] = {"stake-id": stake_id}
    env = {"AITBC_WALLET_DIR": DEFAULT_WALLET_DIR}

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command(
        "wallet",
        "unstake",
        None,
        group_options=group_options,
        subcommand_options=subcommand_options,
        env=env,
    )
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(
        _run_aitbc_cli(
            target,
            "wallet",
            "unstake",
            None,
            None,
            "json",
            group_options=group_options,
            subcommand_options=subcommand_options,
            env=env,
        )
    )


# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def init_governance_profile(
    user_id: Annotated[
        str,
        Field(description="User ID (JWT sub or wallet address) the DAO governance profile belongs to."),
    ],
    voting_power: Annotated[
        float,
        Field(description="Initial voting power (admin only; ignored when the profile already exists)."),
    ] = 0.0,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Create or fetch a DAO governance profile (admin bootstrap, #2337).

    Wraps ``aitbc governance profile init`` → ``POST /v1/governance/profiles``.
    Requires the admin-aware ``auth login`` credential on the target host —
    ``initial_voting_power`` only applies at creation; use
    ``set_governance_voting_power`` for profiles that already exist.
    """
    options: dict[str, str | None] = {"user-id": user_id, "voting-power": str(voting_power)}

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("governance", ["profile", "init"], None, options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "governance", ["profile", "init"], None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def delegate_governance_votes(
    profile_id: Annotated[
        str,
        Field(description="Delegator profile ID."),
    ],
    delegatee_id: Annotated[
        str,
        Field(description="Profile ID receiving the delegated voting power."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Delegate a DAO profile's voting power to another profile (#2337).

    Wraps ``aitbc governance profile delegate`` →
    ``POST /v1/governance/profiles/{id}/delegate``. Caller-bound for client
    JWTs (the profile must belong to the caller); admin JWTs bypass.
    """
    options: dict[str, str | None] = {"profile-id": profile_id, "delegatee-id": delegatee_id}

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("governance", ["profile", "delegate"], None, options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "governance", ["profile", "delegate"], None, options, "json"))


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def set_governance_voting_power(
    profile_id: Annotated[
        str,
        Field(description="Profile ID to update."),
    ],
    voting_power: Annotated[
        float,
        Field(description="New own voting power (>= 0; admin only)."),
    ],
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the destructive action."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Set a DAO profile's own voting power (admin, #2337).

    Wraps ``aitbc governance profile power`` →
    ``POST /v1/governance/profiles/{id}/voting-power``. The escape hatch for
    profiles auto-created at 0 — ``initial_voting_power`` is ignored for
    existing profiles.
    """
    options: dict[str, str | None] = {"profile-id": profile_id, "voting-power": str(voting_power)}

    target = _host_for_role(role, host)
    command = _build_aitbc_cli_command("governance", ["profile", "power"], None, options, "json")
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(_run_aitbc_cli(target, "governance", ["profile", "power"], None, options, "json"))
