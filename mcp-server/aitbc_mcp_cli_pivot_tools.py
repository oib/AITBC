"""Generic AITBC CLI pivot MCP tools (split from aitbc_mcp_server, #1867)."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from aitbc_mcp_mask import mask_envelope

from aitbc_mcp_server import (
    AITBC_CLI,
    ALL_AITBC_GROUPS,
    NodeRole,
    _aitbc_cli_read_tool,
    _build_aitbc_cli_command,
    _build_dry_run,
    _execution_context,
    _host_for_role,
    _is_aitbc_subcommand_destructive,
    _is_aitbc_subcommand_read_only,
    _json,
    _options_suggest_mutation,
    _require_confirm,
    _run_aitbc_cli,
    _run_remote,
    _validate_cli_env_cwd,
    mcp,
)

# ---------------------------------------------------------------------------
# AITBC CLI pivot tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def run_aitbc_cli(
    group: Annotated[
        str,
        Field(description="Live aitbc CLI group (e.g. 'wallet', 'market', 'ai', 'node')."),
    ],
    subcommand: Annotated[
        str | list[str],
        Field(
            description="Subcommand to run — a string ('sell lock' is split like a shell) or a path list (['bridge', 'sell', 'lock'])."
        ),
    ],
    args: Annotated[
        list[str] | None,
        Field(description="Positional arguments for the subcommand."),
    ] = None,
    options: Annotated[
        dict[str, str | list[str] | None] | None,
        Field(description="Options as --key=value. Pass a list for repeated options, or null for boolean flags."),
    ] = None,
    group_options: Annotated[
        dict[str, str | list[str] | None] | None,
        Field(
            description="Group-level options placed before the subcommand, e.g. {'wallet-name': 'default'} for 'aitbc wallet --wallet-name default <subcommand>'."
        ),
    ] = None,
    output_format: Annotated[
        Literal["json", "yaml", "csv", "table"],
        Field(description="Output format; JSON is preferred for machine parsing."),
    ] = "json",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Show the command without executing it."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm the action."),
    ] = False,
    timeout: Annotated[
        int,
        Field(description="Timeout in seconds.", ge=5, le=600),
    ] = 120,
    env: Annotated[
        dict[str, str] | None,
        Field(
            description=(
                "Extra environment variables for the remote command. Allow-listed names only: HOME or "
                "non-secret AITBC_* names; every value must be a path under /var/tmp/ (scratch space). "
                "Applied as a POSIX env prefix on the remote shell — SSH SendEnv is not used."
            )
        ),
    ] = None,
    cwd: Annotated[
        str | None,
        Field(
            description=(
                "Working directory for the remote command; must be a path under /var/tmp/ (scratch space). "
                "Runs as `cd <cwd> && <command>` on the remote shell."
            )
        ),
    ] = None,
) -> str:
    """Run an aitbc CLI command with structured group, subcommand, args and options.

    This is the generic pivot for any live aitbc CLI operation not covered by a
    dedicated wrapper. Destructive subcommands require ``dry_run=false`` and
    ``confirm=true``. Read-only subcommands require ``dry_run=false`` to run.

    Examples:
      - group="wallet", subcommand="list"
      - group="wallet", subcommand="rewards", group_options={"wallet-name": "default"}
      - group="wallet", subcommand="balance", args=["genesis"]
      - group="ai", subcommand="status", args=["<job-id>"]
      - group="market", subcommand="status", args=["<order-id>"]
      - group="node", subcommand="info", args=["<node-id>"]
      - scratch play: group="wallet", subcommand="create", env={"HOME": "/var/tmp/scratch", "AITBC_WALLET_DIR": "/var/tmp/scratch/wallets"}, cwd="/var/tmp/scratch"
    """
    target = _host_for_role(role, host)
    if group not in ALL_AITBC_GROUPS:
        return _json(
            {
                "error": f"unknown aitbc group: {group}",
                "allowed_groups": sorted(ALL_AITBC_GROUPS),
            }
        )
    env_error = _validate_cli_env_cwd(env, cwd)
    if env_error:
        return _json({"error": env_error})

    try:
        command = _build_aitbc_cli_command(
            group,
            subcommand,
            args,
            options,
            output_format,
            group_options=group_options,
            env=env,
            cwd=cwd,
        )
    except ValueError as e:
        return _json({"error": f"invalid subcommand or options: {e}"})
    destructive = _is_aitbc_subcommand_destructive(subcommand, group, args)

    # MCP-GATE-1 (#1672): the no-confirm path is now the read-only ALLOWLIST,
    # not the destructive denylist — an unlisted mutating verb can no longer
    # slip through just because nobody catalogued it.  Anything without a
    # typed read tool, plus any invocation whose option names look mutating,
    # needs dry_run=false + confirm=true.  Residual gap (documented on the
    # issue): a mutation hidden behind an innocuous flag name on an
    # allowlisted read path is still possible — the CLI itself is the last
    # line there.
    read_only = _is_aitbc_subcommand_read_only(subcommand, group, args)
    option_mutation = _options_suggest_mutation(options, group_options)

    if dry_run:
        return _json(_build_dry_run("Set dry_run=false to execute.", command, host=target))

    if (destructive or option_mutation or not read_only) and not confirm:
        return _json(
            {
                "error": "Confirmation required",
                "command": command,
                **_execution_context(target),
                "note": ("This aitbc subcommand may mutate state. Pass dry_run=false and confirm=true to execute."),
            }
        )

    return _json(
        _run_aitbc_cli(
            target,
            group,
            subcommand,
            args,
            options,
            output_format,
            timeout,
            group_options=group_options,
            env=env,
            cwd=cwd,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def read_aitbc_cli(
    group: Annotated[
        str,
        Field(description="Live aitbc CLI group (e.g. 'wallet', 'market', 'ai')."),
    ],
    subcommand: Annotated[
        list[str] | None,
        Field(
            description="Subcommand path as a list (e.g. ['service', 'list']). Pass None for top-level commands like 'version'."
        ),
    ] = None,
    args: Annotated[
        list[str] | None,
        Field(description="Positional arguments for the subcommand."),
    ] = None,
    options: Annotated[
        dict[str, str | list[str] | None] | None,
        Field(
            description="Subcommand options as --key=value. Pass a list for multi-value options, or null for boolean flags."
        ),
    ] = None,
    group_options: Annotated[
        dict[str, str | list[str] | None] | None,
        Field(description="Group-level options placed before the subcommand, e.g. {'wallet-name': 'default'}."),
    ] = None,
    output_format: Annotated[
        Literal["json", "yaml", "csv", "table"],
        Field(description="Output format; JSON is preferred for machine parsing."),
    ] = "json",
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the command runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
    timeout: Annotated[
        int,
        Field(description="Timeout in seconds.", ge=5, le=600),
    ] = 120,
    env: Annotated[
        dict[str, str] | None,
        Field(
            description=(
                "Extra environment variables for the remote command. Allow-listed names only: HOME or "
                "non-secret AITBC_* names; every value must be a path under /var/tmp/ (scratch space). "
                "Applied as a POSIX env prefix on the remote shell — SSH SendEnv is not used."
            )
        ),
    ] = None,
    cwd: Annotated[
        str | None,
        Field(
            description=(
                "Working directory for the remote command; must be a path under /var/tmp/ (scratch space). "
                "Runs as `cd <cwd> && <command>` on the remote shell."
            )
        ),
    ] = None,
) -> str:
    """Generic read-only wrapper for any aitbc CLI command.

    This is a fallback for commands that do not yet have a dedicated typed tool.
    Destructive subcommands are rejected; use run_aitbc_cli for mutating operations.

    Examples:
      - group="version"
      - group="wallet", subcommand=["rewards"]
      - group="ai", subcommand=["service", "list"]
      - group="market", subcommand=["list"], group_options={"mine": None}
      - scratch HOME: group="wallet", subcommand=["list"], env={"HOME": "/var/tmp/scratch"}
    """
    target = _host_for_role(role, host)
    if group not in ALL_AITBC_GROUPS:
        return _json(
            {
                "error": f"unknown aitbc group: {group}",
                "allowed_groups": sorted(ALL_AITBC_GROUPS),
            }
        )
    if _is_aitbc_subcommand_destructive(subcommand, group, args):
        return _json(
            {
                "error": "subcommand is destructive",
                "subcommand": subcommand,
                "note": "Use run_aitbc_cli for mutating operations; destructive subcommands require dry_run=false and confirm=true.",
            }
        )
    if not _is_aitbc_subcommand_read_only(subcommand, group, args):
        return _json(
            {
                "error": "subcommand is not a known read-only path",
                "subcommand": subcommand,
                "note": "read_aitbc_cli only runs paths that carry a typed read tool (#849). "
                "Use run_aitbc_cli for everything else; destructive subcommands require dry_run=false and confirm=true.",
            }
        )
    env_error = _validate_cli_env_cwd(env, cwd)
    if env_error:
        return _json({"error": env_error})
    return _json(
        _run_aitbc_cli(
            target,
            group,
            subcommand,
            args,
            options,
            output_format,
            timeout,
            group_options=group_options,
            env=env,
            cwd=cwd,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_aitbc_cli_group(
    group: Annotated[
        str,
        Field(description="Live aitbc CLI group to describe (e.g. 'wallet', 'market')."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show the help output for a live aitbc CLI group."""
    target = _host_for_role(role, host)
    if group not in ALL_AITBC_GROUPS:
        return _json(
            {
                "error": f"unknown aitbc group: {group}",
                "allowed_groups": sorted(ALL_AITBC_GROUPS),
            }
        )
    return _json(_run_remote(target, f"{AITBC_CLI} {shlex.quote(group)} --help"))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_aitbc_version(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the installed aitbc CLI version."""
    return _aitbc_cli_read_tool(role, host, "version", subcommand=None)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_auth_status(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show stored aitbc CLI authentication credentials (values are masked)."""
    return _aitbc_cli_read_tool(role, host, "auth", "status")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_wallets(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List wallets known to the aitbc CLI."""
    return _aitbc_cli_read_tool(role, host, "wallet", "list")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_wallet_balance(
    wallet_name: Annotated[
        str,
        Field(description="Wallet name to query."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the balance of a named wallet."""
    return _aitbc_cli_read_tool(role, host, "wallet", "balance", group_options={"wallet-name": wallet_name})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_wallet_transactions(
    wallet_name: Annotated[
        str,
        Field(description="Wallet name to query."),
    ],
    limit: Annotated[
        int | None,
        Field(description="Maximum number of transactions to return.", ge=1),
    ] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List blockchain transactions for a wallet."""
    subcommand_options: dict[str, str] = {}
    if limit is not None:
        subcommand_options["limit"] = str(limit)
    return _aitbc_cli_read_tool(
        role,
        host,
        "wallet",
        "transactions",
        group_options={"wallet-name": wallet_name},
        subcommand_options=subcommand_options,
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_ai_jobs(
    limit: Annotated[
        int | None,
        Field(description="Maximum number of jobs to return.", ge=1),
    ] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List AI jobs."""
    options: dict[str, str] = {}
    if limit is not None:
        options["limit"] = str(limit)
    return _aitbc_cli_read_tool(role, host, "ai", "jobs", options=options)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ai_job_status(
    job_id: Annotated[
        str,
        Field(description="AI job ID."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the status of an AI job."""
    return _aitbc_cli_read_tool(role, host, "ai", "status", options={"job-id": job_id})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_ai_job_results(
    job_id: Annotated[
        str,
        Field(description="AI job ID."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the results of a completed AI job."""
    return _aitbc_cli_read_tool(role, host, "ai", "results", options={"job-id": job_id})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_market_offers(
    limit: Annotated[
        int | None,
        Field(description="Maximum number of offers to return (post-filter).", ge=1),
    ] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List GPU/software market offers and bids.

    The AITBC CLI ``market list`` does not support a ``--limit`` option, so the
    limit is applied after fetching the list.
    """
    response = _aitbc_cli_read_tool(role, host, "market", "list")
    if limit is None:
        return response
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        return response
    offers = parsed.get("json")
    if offers is None:
        try:
            stdout = parsed.get("stdout", "[]")
            offers, _ = json.JSONDecoder().raw_decode(stdout)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return response
    if isinstance(offers, list):
        offers = offers[:limit]
        parsed["json"] = offers
        parsed["stdout"] = json.dumps(offers)
    return json.dumps(mask_envelope(parsed))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_market_status(
    order_id: Annotated[
        str,
        Field(description="Market order/escrow ID."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Check the status of a GPU order including on-chain escrow."""
    return _aitbc_cli_read_tool(role, host, "market", "status", args=[order_id])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_aitbc_node_config(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List nodes configured in the aitbc CLI."""
    return _aitbc_cli_read_tool(role, host, "node", "list")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_node_info(
    node_id: Annotated[
        str,
        Field(description="Node ID to look up."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get detailed information about a configured aitbc node."""
    return _aitbc_cli_read_tool(role, host, "node", "info", args=[node_id])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_accounts(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """List accounts tracked by the aitbc CLI."""
    return _aitbc_cli_read_tool(role, host, "account", "list")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_account(
    address: Annotated[
        str,
        Field(description="Account address to look up."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get account information for a single address."""
    return _aitbc_cli_read_tool(role, host, "account", "get", options={"address": address})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_bond_status(
    provider: Annotated[
        str,
        Field(description="Provider ID or address to look up."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show a provider's performance bond eligibility status."""
    return _aitbc_cli_read_tool(role, host, "bond", "status", args=[provider])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def list_pending_transactions(
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get pending aitbc transactions."""
    return _aitbc_cli_read_tool(role, host, "transactions", "pending")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_transaction_status(
    tx_hash: Annotated[
        str,
        Field(description="Transaction hash."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Get the status of a transaction."""
    return _aitbc_cli_read_tool(role, host, "transactions", "status", args=[tx_hash])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def search_transactions(
    address: Annotated[
        str,
        Field(description="Address or node ID to search for."),
    ],
    limit: Annotated[
        int | None,
        Field(description="Maximum number of transactions to return.", ge=1),
    ] = None,
    use_explorer: Annotated[
        bool,
        Field(description="Use the Explorer API instead of RPC."),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Search transactions by address or node ID."""
    options: dict[str, str] = {}
    if limit is not None:
        options["limit"] = str(limit)
    if use_explorer:
        options["use-explorer"] = ""
    return _aitbc_cli_read_tool(role, host, "transactions", "search", args=[address], options=options)


def _service_logs_error(
    service: str,
    since: str | None,
    grep: str | None,
    priority: str | None,
    severity_pattern: bool,
) -> dict[str, Any] | None:
    """The get_service_logs input-validation failure, or None."""
    if re.search(r"[;&|<>$`\\!\n\r]", service):
        return {"error": "invalid service name", "service": service}
    for name, value in (("since", since), ("grep", grep)):
        if value is None:
            continue
        if len(value) > 200:
            return {"error": f"{name} too long (max 200 chars)"}
        # values are shlex-quoted into --opt=<value>, so shell metacharacters
        # are inert — mirror the CLI's logs validation (newline/CR/NUL only)
        if re.search(r"[\n\r\x00]", value):
            return {"error": f"invalid {name}", name: value}
    if grep is not None and severity_pattern:
        return {"error": "grep and severity_pattern are mutually exclusive"}
    if priority is not None:
        # server-side validation only — the CLI enforces the level vocabulary
        if len(priority) > 40 or re.search(r"[^A-Za-z0-9.]", priority):
            return {"error": "invalid priority", "priority": priority}
    return None


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_service_logs(
    service: Annotated[
        str,
        Field(description="systemd unit name, e.g. 'aitbc-blockchain-rpc'."),
    ],
    lines: Annotated[
        int,
        Field(description="Number of recent log lines to return.", ge=1, le=1000),
    ] = 50,
    since: Annotated[
        str | None,
        Field(description="Only entries newer than this journalctl time spec, e.g. '10 min ago' or '2026-10-13 00:00'."),
    ] = None,
    grep: Annotated[
        str | None,
        Field(description="Filter entries matching this journalctl --grep pattern (max 200 chars)."),
    ] = None,
    priority: Annotated[
        str | None,
        Field(
            description="journalctl -p priority filter: a level name/number (err, warning, 3) or a 'from..to' range (err..warning)."
        ),
    ] = None,
    severity_pattern: Annotated[
        bool,
        Field(
            description="Filter on app-level severity text (WARN/ERROR/CRITICAL) — app logs carry no journal "
            "priority. Mutually exclusive with grep; the pattern is fixed server-side."
        ),
    ] = False,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Tail systemd journal logs for an AITBC service."""
    target = _host_for_role(role, host)
    validation = _service_logs_error(service, since, grep, priority, severity_pattern)
    if validation is not None:
        return _json(validation)
    options = {"service": service, "lines": str(lines)}
    if since is not None:
        options["since"] = since
    if grep is not None:
        options["grep"] = grep
    if priority is not None:
        options["priority"] = priority
    if severity_pattern:
        options["severity-pattern"] = ""
    return _json(
        _run_aitbc_cli(
            target,
            "system",
            "logs",
            [],
            options,
            output_format="json",
            timeout=30,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_service_status(
    service: Annotated[
        str,
        Field(description="systemd unit name, e.g. 'aitbc-coordinator-api'."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show full systemd status output for a single AITBC service via the CLI."""
    target = _host_for_role(role, host)
    if re.search(r"[^A-Za-z0-9_.@-]", service):
        return _json({"error": "invalid service name", "service": service})
    return _json(
        _run_aitbc_cli(
            target,
            "system",
            "status",
            [],
            {"service": service},
            output_format="json",
            timeout=30,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_systemd_unit(
    service: Annotated[
        str,
        Field(description="systemd unit name, e.g. 'aitbc-coordinator-api'."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Display the systemd unit file for a service via the CLI."""
    target = _host_for_role(role, host)
    if re.search(r"[^A-Za-z0-9_.@-]", service):
        return _json({"error": "invalid service name", "service": service})
    return _json(
        _run_aitbc_cli(
            target,
            "system",
            "cat",
            [],
            {"service": service},
            output_format="json",
            timeout=30,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_systemd_show(
    service: Annotated[
        str,
        Field(description="systemd unit name, e.g. 'aitbc-coordinator-api'."),
    ],
    properties: Annotated[
        str | None,
        Field(description="Comma-separated unit properties to show (e.g. 'ActiveState,SubState,MemoryDenyWriteExecute')."),
    ] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Show selected systemd show properties for a service via the CLI."""
    target = _host_for_role(role, host)
    if re.search(r"[^A-Za-z0-9_.@-]", service):
        return _json({"error": "invalid service name", "service": service})
    if properties:
        if re.search(r"[^A-Za-z0-9_,=]", properties):
            return _json({"error": "invalid properties", "properties": properties})
    options: dict[str, str | None] = {"service": service}
    if properties:
        options["properties"] = properties
    return _json(
        _run_aitbc_cli(
            target,
            "system",
            "show",
            [],
            options,
            output_format="json",
            timeout=30,
        )
    )


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_remote_file(
    file_path: Annotated[
        str,
        Field(description="Absolute path to a file under /opt/aitbc, /etc/aitbc, /var/log/aitbc, or /var/lib/aitbc."),
    ],
    role: Annotated[
        NodeRole | None,
        Field(description="Node role to query."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Read a remote AITBC configuration, log, or data file."""
    target = _host_for_role(role, host)
    if re.search(r"[;&|<>$`\\!\n\r]", file_path):
        return _json({"error": "invalid file path", "path": file_path})
    if ".." in Path(file_path).parts or not file_path.startswith("/"):
        return _json({"error": "invalid file path", "path": file_path})
    return _json(
        _run_aitbc_cli(
            target,
            "system",
            "file",
            [],
            {"path": file_path},
            output_format="json",
            timeout=30,
        )
    )


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def restart_service(
    service: Annotated[
        str,
        Field(description="systemd unit name, e.g. 'aitbc-coordinator-api'."),
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
        Field(description="Node role where the service runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
) -> str:
    """Restart a single AITBC systemd service."""
    target = _host_for_role(role, host)
    if re.search(r"[^A-Za-z0-9_.@-]", service):
        return _json({"error": "invalid service name", "service": service})
    command = _build_aitbc_cli_command(
        "system",
        "restart",
        [],
        {"service": service},
        output_format="json",
    )
    guard = _require_confirm(dry_run, confirm, command, host=target)
    if guard is not None:
        return _json(guard)
    return _json(
        _run_aitbc_cli(
            target,
            "system",
            "restart",
            [],
            {"service": service},
            output_format="json",
            timeout=120,
        )
    )


# ---------------------------------------------------------------------------
