#!/usr/bin/env python3
"""Generate typed MCP tools from the aitbc CLI command tree.

The script walks all Click commands, extracts options and positional arguments,
classifies commands as read-only or safeguarded, and writes a Python module with
one ``@mcp.tool`` wrapper per command.  Read-only tools call
``_aitbc_cli_read_tool`` directly; safeguarded tools add ``dry_run`` and
``confirm`` guards.

Usage:

    python scripts/dev/generate_mcp_cli_tools.py --output mcp-server/aitbc_mcp_cli_tools_generated.py

Modes:
    safe          Read-only commands only (default).
    safeguarded   Read-only + mutating commands with dry_run/confirm guards.
    all           Every command except an explicit skip list.

"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_ROOT = REPO_ROOT / "cli"
MCP_ROOT = REPO_ROOT / "mcp-server"

if str(CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(CLI_ROOT))

import click

from aitbc_cli.core.main import cli
from aitbc_cli.utils.help_quality import walk_commands


# Tokens that, when present anywhere in a command path, mark the command as
# potentially mutating.  A command is only classified as "read-only" when no
# token appears in this set and its leaf token is in SAFE_LEAF_TOKENS.
DESTRUCTIVE_TOKENS = {
    "submit",
    "cancel",
    "refund",
    "accept",
    "create",
    "delete",
    "send",
    "spend",
    "stake",
    "unstake",
    "fund",
    "import-wallet",
    "restore",
    "backup",
    "propose",
    "vote",
    "execute",
    "start",
    "stop",
    "restart",
    "offer",
    "process",
    "run",
    "transcribe",
    "buy",
    "sell",
    "trade",
    "order",
    "deposit",
    "withdraw",
    "deploy",
    "update",
    "multisig-propose",
    "multisig-sign",
    "liquidity-stake",
    "liquidity-unstake",
    "rate",
    "publish",
    "register",
    "unregister",
    "bind",
    "escrow",
    "appeal",
    "lock",
    "release",
    "slash",
    "top-up",
    "batch",
    "login",
    "logout",
    "mint-ait",
    "withdraw-eth",
    "sync-ratings",
    "offer-disable",
    "set",
    "edit",
    "reset",
    "unset",
    "import-config",
    "export",
    "switch",
    "remove",
    "deregister",
    "claim",
    "redeem",
    "burn",
    "mint",
    "run-script",
    "force-sync",
    "sync",
    "add",
    "migrate",
    "destroy",
    "host",
    "pin",
    "unpin",
    "upload",
    "download",
    "add-peer",
    "remove-peer",
    "reboot",
    "shutdown",
    "clear-cache",
    "purge",
    "replace",
}

# Leaf tokens that are considered safe *when none of the path tokens are
# destructive*.  This is conservative: a leaf token alone does not make a
# command read-only, it only allows classification if the rest of the path is
# non-destructive and no force override applies.
SAFE_LEAF_TOKENS = {
    "address",
    "addresses",
    "all",
    "alerts",
    "allocation",
    "architect",
    "audit",
    "balance",
    "benchmark",
    "block",
    "blocks",
    "block-by-hash",
    "blocks-by-address",
    "bridge-status",
    "campaign",
    "campaigns",
    "campaign-stats",
    "cat",
    "chain-head",
    "check",
    "checks",
    "config",
    "configs",
    "cron",
    "dashboard",
    "delegates",
    "delegations",
    "describe",
    "difficulty",
    "discover",
    "distribution-stats",
    "env",
    "environment",
    "estimate",
    "examples",
    "explorer",
    "fee",
    "file",
    "gas",
    "get",
    "hash",
    "health",
    "height",
    "help",
    "history",
    "info",
    "inbox",
    "island",
    "islands",
    "job",
    "jobs",
    "latest",
    "latest-blocks",
    "leaderboard",
    "list",
    "log",
    "logs",
    "match",
    "metrics",
    "model",
    "models",
    "monitor",
    "network",
    "network-stats",
    "non-empty-blocks",
    "offer",
    "offers",
    "operator",
    "operators",
    "oracle",
    "path",
    "paths",
    "peers",
    "pool",
    "pools",
    "profile",
    "profiles",
    "provider",
    "providers",
    "proposals",
    "quote",
    "rate",
    "rates",
    "ratings",
    "read",
    "receipt",
    "receipts",
    "rewards",
    "rich",
    "richest",
    "search",
    "security",
    "security-status",
    "service",
    "service-list",
    "service-status",
    "services",
    "show",
    "simulate",
    "size",
    "sla",
    "state",
    "status",
    "stat",
    "statistics",
    "stats",
    "staking-info",
    "summary",
    "supply",
    "swaps",
    "swarm-key",
    "sync-status",
    "top",
    "top-addresses",
    "transaction",
    "transactions",
    "transaction-by-hash",
    "trust",
    "trust-score",
    "usage",
    "validate",
    "validation",
    "validators",
    "version",
    "view",
    "vote",
    "votes",
    "voters",
    "wallet",
    "wallets",
}

# Explicit overrides for commands where the token heuristic is wrong.
FORCE_READ_ONLY_PATHS: set[tuple[str, ...]] = {
    ("market", "match"),
    ("market", "list"),
    ("market", "status"),
    ("market", "providers"),
    ("market", "ratings"),
    ("wallet", "rewards"),
    ("wallet", "staking-info"),
    ("wallet", "transactions"),
    ("wallet", "address"),
    ("wallet", "info"),
    ("ai", "stats"),
    ("ai", "distribution-stats"),
    ("ai", "service", "list"),
    ("ai", "service", "service-status"),
    ("blockchain", "sync-status"),
    ("blockchain", "monitor"),
    ("node", "list"),
    ("node", "info"),
    ("node", "monitor"),
    ("system", "status"),
    ("system", "show"),
    ("system", "logs"),
    ("system", "cron"),
    ("system", "config"),
    ("system", "file"),
    ("explorer", "block"),
    ("explorer", "transaction"),
    ("explorer", "chain-head"),
    ("explorer", "latest-blocks"),
    ("governance", "list"),
    ("governance", "status"),
    ("governance", "get"),
    ("ipfs", "list"),
    ("bridge", "status"),
    ("reputation", "leaderboard"),
    ("monitor", "dashboard"),
    ("monitor", "metrics"),
    ("analytics", "summary"),
    ("analytics", "dashboard"),
    ("crosschain", "status"),
    ("crosschain", "swaps"),
    ("crosschain", "rates"),
    ("crosschain", "pools"),
}

FORCE_DESTRUCTIVE_PATHS: set[tuple[str, ...]] = {
    ("trade", "match"),
    ("trade", "get"),
    ("http", "call"),
    ("agent-msg", "send"),
    ("agent-comm", "collaborate"),
    ("monitor", "alerts"),
    ("monitor", "webhooks"),
    ("dispute", "resolve"),
    ("reputation", "feedback"),
    ("energy", "provider", "rate"),
    ("market", "gpu", "buy"),
    ("market", "gpu", "quote"),
    ("market", "gpu", "refund"),
    ("market", "gpu", "release"),
    ("market", "gpu", "status"),
}

# Commands we never generate a dedicated tool for, even in safeguarded/all mode.
# They are either too dangerous, too operator-specific, or covered by explicit
# tools elsewhere.
FORCE_SKIP_PATHS: set[tuple[str, ...]] = {
    ("genesis", "reset"),
    ("wallet", "delete"),
    ("wallet", "import-wallet"),
    ("config", "reset"),
    ("blockchain", "destroy"),
    ("node", "reboot"),
    ("node", "shutdown"),
    ("system", "reboot"),
    ("system", "shutdown"),
    ("operations",),
}

# Tokens that identify a quantity of money.  Options whose name contains one
# of these tokens and whose CLI type is float are emitted as `Decimal` so the
# generated tools comply with the repo's no-float-money rule.
MONEY_TOKENS = {
    "amount",
    "amounts",
    "balance",
    "balances",
    "budget",
    "budgets",
    "price",
    "prices",
    "fee",
    "fees",
    "cost",
    "costs",
    "earnings",
    "reward",
    "rewards",
    "payout",
    "payouts",
    "payment",
    "payments",
    "funding",
    "funds",
    "revenue",
    "spend",
    "spending",
    "spent",
    "subtotal",
    "deposit",
    "deposits",
    "withdrawal",
    "withdrawals",
    "wei",
    "satoshi",
    "tip",
    "value",
    "total",
}

SKIP_OPTION_NAMES = {"help", "format", "output", "output_format", "output-format"}

# Names we already use for MCP routing/safety parameters in every generated tool.
RESERVED_PY_NAMES = {"role", "host", "timeout", "dry_run", "confirm"}


def existing_tool_names(files: list[Path] | None = None) -> set[str]:
    """Return all existing @mcp.tool function names."""
    if files is None:
        files = [
            MCP_ROOT / "aitbc_mcp_server.py",
            MCP_ROOT / "aitbc_mcp_rpc_tools.py",
            MCP_ROOT / "aitbc_mcp_cli_tools.py",
            MCP_ROOT / "aitbc_mcp_liquidity_tools.py",
            MCP_ROOT / "aitbc_mcp_zk_tools.py",
        ]
    names: set[str] = set()
    for f in files:
        if not f.exists():
            continue
        text = f.read_text()
        for match in re.finditer(r"@mcp\.tool", text):
            nxt = re.search(r"def\s+(\w+)\s*\(", text[match.end() :])
            if nxt:
                names.add(nxt.group(1))
    return names


def path_to_func_name(path: tuple[str, ...]) -> str:
    return "aitbc_" + "_".join(p.replace("-", "_") for p in path)


def path_to_cli_name(path: tuple[str, ...]) -> str:
    return " ".join(path)


def get_flag_name(param: click.Option) -> str | None:
    long = [o for o in param.opts if o.startswith("--")]
    if long:
        return max(long, key=len).lstrip("-")
    short = [o for o in param.opts if o.startswith("-") and len(o) == 2]
    if short:
        return short[0].lstrip("-")
    return None


def py_type(param: click.Parameter, choices: list[str] | None = None) -> str:
    if choices:
        # Limit literal size and avoid unreadable docstrings.
        display = choices[:32]
        if len(choices) > 32:
            return "str"
        return "Literal[" + ", ".join(repr(c) for c in display) + "]"
    tname = type(param.type).__name__
    if tname == "IntParamType":
        return "int"
    if tname == "FloatParamType":
        return "float"
    if tname == "BoolParamType":
        return "bool"
    if tname == "Path":
        return "str"
    if tname == "FuncParamType":
        return "str"
    return "str"


def quote(s: str | None) -> str:
    if s is None:
        return '""'
    out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{out}"'


def classify_command(path: tuple[str, ...]) -> str:
    """Return 'read_only', 'safeguarded', or 'skip' for a command path."""
    if path in FORCE_SKIP_PATHS:
        return "skip"
    if path in FORCE_READ_ONLY_PATHS:
        return "read_only"
    if path in FORCE_DESTRUCTIVE_PATHS:
        return "safeguarded"

    normalized = [p.replace("-", "_") for p in path]
    for p in normalized:
        if p in DESTRUCTIVE_TOKENS:
            return "safeguarded"

    leaf = path[-1].replace("-", "_")
    if leaf in SAFE_LEAF_TOKENS and not any(p in DESTRUCTIVE_TOKENS for p in normalized):
        return "read_only"

    return "safeguarded"


def is_excluded_option(param: click.Option) -> bool:
    name = (param.name or "").replace("-", "_")
    return name in SKIP_OPTION_NAMES or (param.hidden is True)


def _unique_py_name(base: str, reserved_suffix: str, seen: set[str]) -> str:
    """Return a collision-free, non-reserved parameter name and record it.

    ``base`` is deduplicated against ``seen`` with a ``_N`` suffix; when the
    result collides with a reserved MCP routing/safety name it becomes
    ``{base}_{reserved_suffix}`` padded with ``_`` until unique.
    """
    py_name = base
    if py_name in seen:
        suffix = 2
        while f"{py_name}_{suffix}" in seen:
            suffix += 1
        py_name = f"{py_name}_{suffix}"
    if py_name in RESERVED_PY_NAMES:
        py_name = f"{py_name}_{reserved_suffix}"
        while py_name in seen:
            py_name = f"{py_name}_"
    seen.add(py_name)
    return py_name


def _parse_option(param: click.Option, order: int, seen_names: set[str]) -> dict[str, Any] | None:
    """Extract one Click option into a param spec, or None when it is skipped."""
    if is_excluded_option(param):
        return None
    flag = get_flag_name(param)
    if not flag:
        return None
    is_flag = getattr(param, "is_flag", False) and type(param.type).__name__ == "BoolParamType"
    multiple = getattr(param, "multiple", False) or getattr(param, "nargs", 1) != 1
    choices = None
    if isinstance(param.type, click.Choice):
        choices = list(param.type.choices)
    ptype = py_type(param, choices)
    if multiple:
        ptype = f"list[{ptype}]" if choices else "list[str]"
    required = bool(param.required) and not is_flag
    help_text = (param.help or "").strip()
    if not help_text:
        help_text = f"{flag} option"
    base = param.name.replace("-", "_") if param.name else flag.replace("-", "_")
    if base in SKIP_OPTION_NAMES:
        return None
    py_name = _unique_py_name(base, "opt", seen_names)
    if ptype == "float" and any(t in MONEY_TOKENS for t in py_name.split("_")):
        ptype = "Decimal"
    return {
        "py_name": py_name,
        "flag": flag,
        "type": ptype,
        "is_flag": is_flag,
        "multiple": multiple,
        "required": required,
        "help": help_text,
        "order": order,
    }


def _parse_argument(param: click.Argument, order: int, seen_names: set[str]) -> dict[str, Any]:
    """Extract one Click positional argument into a param spec."""
    py_name = _unique_py_name((param.name or "arg").replace("-", "_"), "arg", seen_names)
    nargs = getattr(param, "nargs", 1)
    multiple = nargs == -1 or nargs > 1
    ptype = "list[str]" if multiple else "str"
    required = bool(getattr(param, "required", True)) and not multiple
    if multiple:
        required = False
    return {
        "py_name": py_name,
        "type": ptype,
        "multiple": multiple,
        "required": required,
        "help": f"Positional argument: {param.name}",
        "order": order,
    }


def parse_command(cmd: click.Command, path: tuple[str, ...]) -> dict[str, Any]:
    """Extract parameters for one command."""
    options: list[dict[str, Any]] = []
    positional: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for i, param in enumerate(cmd.params):
        if isinstance(param, click.Option):
            option = _parse_option(param, i, seen_names)
            if option is not None:
                options.append(option)
        elif isinstance(param, click.Argument):
            positional.append(_parse_argument(param, i, seen_names))

    return {
        "path": path,
        "command": cmd,
        "options": options,
        "positional": positional,
        "help": (cmd.help or "").strip(),
        "callback": cmd.callback,
    }


def build_param_schema(params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort required first, then by declaration order."""
    return sorted(params, key=lambda p: (not p["required"], p["order"]))


def render_field(param: dict[str, Any], *, is_timeout: bool = False) -> str:
    extras = ""
    if is_timeout:
        extras = ", ge=5, le=600"
    return f"Field(description={quote(param['help'])}{extras})"


def _render_signature(spec: dict[str, Any], func_name: str, read_only: bool) -> list[str]:
    """Emit the def line, parameter list and docstring of one tool."""
    all_params = build_param_schema(spec["positional"] + spec["options"])

    lines: list[str] = [f"def {func_name}("]
    for param in all_params:
        ptype = param["type"]
        if not param["required"]:
            ptype = f"{ptype} | None"
        lines.append(f"    {param['py_name']}: Annotated[{ptype}, {render_field(param)}],")
    lines.append('    role: Annotated[NodeRole | None, Field(description="Node role to query.")] = None,')
    lines.append('    host: Annotated[str | None, Field(description="Override the host for this call.")] = None,')
    lines.append('    timeout: Annotated[int, Field(description="Timeout in seconds.", ge=5, le=600)] = 120,')
    if not read_only:
        lines.append('    dry_run: Annotated[bool, Field(description="Show the command without executing it.")] = True,')
        lines.append('    confirm: Annotated[bool, Field(description="Confirm the action.")] = False,')
    lines.append(") -> str:")

    # Docstring
    path = spec["path"]
    short_help = spec["help"].split("\n")[0] if spec["help"] else f"Run `aitbc {path_to_cli_name(path)}`."
    lines.append(f'    """{short_help}."""')
    return lines


def _render_str_map(mapping: dict[str, str]) -> str:
    """Render a ``dict[str, str]`` literal with double-quoted keys and values."""
    return "{" + ", ".join(f"{quote(k)}: {quote(v)}" for k, v in mapping.items()) + "}"


def _render_options_block(spec: dict[str, Any]) -> list[str]:
    """Emit the ``options`` dict via a single ``_collect_options`` call.

    ``locals()`` is passed so the helper can look each parameter up by name;
    the flag/value maps use the python parameter names as keys.
    """
    if not spec["options"]:
        return ["    options: dict[str, Any] = {}"]
    flags = {p["py_name"]: p["flag"] for p in spec["options"] if p["is_flag"]}
    values = {p["py_name"]: p["flag"] for p in spec["options"] if not p["is_flag"]}
    return [
        "    options: dict[str, Any] = _collect_options(",
        "        locals(),",
        f"        flags={_render_str_map(flags)},",
        f"        values={_render_str_map(values)},",
        "    )",
    ]


def _render_args_block(spec: dict[str, Any]) -> list[str]:
    """Emit the ``args`` list built from the positional parameters."""
    positional_names = [p["py_name"] for p in spec["positional"]]
    if not positional_names:
        return ["    args = None"]
    if len(positional_names) == 1:
        p = spec["positional"][0]
        if p["multiple"]:
            return [f"    args = {p['py_name']} or []"]
        return [f"    args = [{p['py_name']}] if {p['py_name']} is not None else []"]
    parts = []
    for p in spec["positional"]:
        if p["multiple"]:
            parts.append(f"({p['py_name']} or [])")
        else:
            parts.append(f"([{p['py_name']}] if {p['py_name']} is not None else [])")
    return ["    args = [] + " + " + ".join(parts)]


def _subcommand_literal(path: tuple[str, ...]) -> str:
    tokens = [quote(p) for p in path[1:]]
    if tokens:
        return "[" + ", ".join(tokens) + "]"
    return "None"


def _render_call_block(spec: dict[str, Any], read_only: bool) -> list[str]:
    """Emit the read-only call or the safeguarded dry_run/confirm call."""
    path = spec["path"]
    group = quote(path[0])
    subcommand = _subcommand_literal(path)

    if read_only:
        return [
            "    return _aitbc_cli_read_tool(",
            "        role,",
            "        host,",
            f"        {group},",
            f"        subcommand={subcommand},",
            "        args=args,",
            "        options=options,",
            "        timeout=timeout,",
            "    )",
        ]

    lines = [
        "    command = _build_aitbc_cli_command(",
        f"        {group},",
        f"        subcommand={subcommand},",
        "        args=args,",
        "        options=options,",
        '        output_format="json",',
        "    )",
        "    if dry_run:",
        '        return _json(_build_dry_run("Set dry_run=false to execute.", command))',
        "    if not confirm:",
        '        return _json({"error": "Confirmation required", "command": command, "note": "This command may mutate state. Pass dry_run=false and confirm=true to execute."})',
        "    target = _host_for_role(role, host)",
        "    return _json(",
        "        _run_aitbc_cli(",
        "            target,",
        f"            {group},",
        f"            subcommand={subcommand},",
        "            args=args,",
        "            options=options,",
        '            output_format="json",',
        "            timeout=timeout,",
        "        )",
        "    )",
    ]
    return lines


def render_function(spec: dict[str, Any], mode: str) -> list[str]:
    path = spec["path"]
    func_name = path_to_func_name(path)
    read_only = spec["mode"] == "read_only"

    if read_only:
        lines = ["@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))"]
    else:
        lines = ["@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))"]

    lines += _render_signature(spec, func_name, read_only)
    lines += _render_options_block(spec)
    lines += _render_args_block(spec)
    lines += _render_call_block(spec, read_only)
    return lines


def build_header(
    mode: str,
    count: int,
    has_read_only: bool,
    has_safeguarded: bool,
    has_decimal: bool,
    has_literal: bool,
    has_options: bool,
) -> list[str]:
    imports = ["    NodeRole,"]
    if has_read_only:
        imports.append("    _aitbc_cli_read_tool,")
    if has_safeguarded:
        imports.extend(
            [
                "    _build_aitbc_cli_command,",
                "    _build_dry_run,",
            ]
        )
    if has_options:
        imports.append("    _collect_options,")
    if has_safeguarded:
        imports.extend(
            [
                "    _host_for_role,",
                "    _json,",
                "    _run_aitbc_cli,",
            ]
        )
    imports.append("    mcp,")
    decimal_import = ["from decimal import Decimal", ""] if has_decimal else []
    typing_imports = ["Annotated", "Any"]
    if has_literal:
        typing_imports.append("Literal")
    return [
        "# ---------------------------------------------------------------------------",
        f"# Auto-generated AITBC CLI MCP wrappers ({mode} mode, {count} tools)",
        "# Generated by: scripts/dev/generate_mcp_cli_tools.py",
        "# Do not edit manually; regenerate instead.",
        "# ---------------------------------------------------------------------------",
        "",
        "from __future__ import annotations",
        "",
        *decimal_import,
        f"from typing import {', '.join(typing_imports)}",
        "",
        "from mcp.types import ToolAnnotations",
        "from pydantic import Field",
        "",
        "from aitbc_mcp_server import (",
        *imports,
        ")",
        "",
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        "-o",
        default=str(MCP_ROOT / "aitbc_mcp_cli_tools_generated.py"),
        help="Output file for the generated module.",
    )
    parser.add_argument(
        "--mode",
        choices=["safe", "safeguarded", "all", "read_only"],
        default="safe",
        help=(
            "Generation mode. 'safe' emits only read-only commands; "
            "'safeguarded' also emits mutating commands with dry_run/confirm guards; "
            "'all' emits every command except the explicit skip list; "
            "'read_only' is an alias for 'safe'."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the generated module to the existing file and exit with status 1 if it would change.",
    )
    parser.add_argument(
        "--split-by-group",
        action="store_true",
        help="Write one module per top-level CLI group plus a master import module.",
    )
    return parser


def _collect_specs(mode: str, existing: set[str]) -> list[dict[str, Any]]:
    """Walk the CLI command tree and return the tool specs to emit for ``mode``."""
    results: list[dict[str, Any]] = []
    for result in walk_commands(cli):
        path = tuple(result["path"])
        if not path:
            continue
        if path in FORCE_SKIP_PATHS:
            continue
        if isinstance(result["command"], click.Group):
            continue

        spec = parse_command(result["command"], path)
        spec["mode"] = classify_command(path)

        if mode == "safe" and spec["mode"] != "read_only":
            continue
        if mode == "safeguarded" and spec["mode"] == "skip":
            continue

        func_name = path_to_func_name(path)
        if func_name in existing:
            continue

        results.append(spec)

    results.sort(key=lambda r: r["path"])
    return results


def main() -> int:
    args = _build_parser().parse_args()

    if args.mode == "read_only":
        args.mode = "safe"

    results = _collect_specs(args.mode, existing_tool_names())

    if args.split_by_group:
        return write_split_modules(results, args)

    out_path = Path(args.output)
    output = render_module(args.mode, results)

    if args.check:
        if out_path.exists() and out_path.read_text() == output:
            print("Generated module is up to date.")
            return 0
        print(f"Generated module would change: {out_path}")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output)
    print(f"Wrote {len(results)} tools to {out_path}")
    return 0


def render_module(mode: str, specs: list[dict[str, Any]]) -> str:
    """Render a single Python module containing the given tool specs."""
    has_read_only = any(spec["mode"] == "read_only" for spec in specs)
    has_safeguarded = any(spec["mode"] == "safeguarded" for spec in specs)
    has_decimal = any(p["type"] == "Decimal" for spec in specs for p in spec["options"] + spec["positional"])
    has_literal = any("Literal[" in p["type"] for spec in specs for p in spec["options"] + spec["positional"])
    has_options = any(spec["options"] for spec in specs)

    lines = build_header(mode, len(specs), has_read_only, has_safeguarded, has_decimal, has_literal, has_options)
    for spec in specs:
        lines.extend(render_function(spec, mode))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_split_modules(results: list[dict[str, Any]], args: argparse.Namespace) -> int:
    """Write one module per top-level CLI group plus a master import module."""
    out_path = Path(args.output)
    output_dir = out_path.parent
    master_name = out_path.stem

    groups: dict[str, list[dict[str, Any]]] = {}
    for spec in results:
        top = spec["path"][0]
        groups.setdefault(top, []).append(spec)

    group_modules: list[str] = []
    for group, specs in sorted(groups.items()):
        safe_group = group.replace("-", "_")
        module_name = f"{master_name}_{safe_group}"
        group_modules.append(module_name)
        group_path = output_dir / f"{module_name}.py"
        group_output = render_module(args.mode, specs)

        if args.check:
            if not group_path.exists() or group_path.read_text() != group_output:
                print(f"Generated module would change: {group_path}")
                return 1
            continue

        group_path.parent.mkdir(parents=True, exist_ok=True)
        group_path.write_text(group_output)
        print(f"Wrote {len(specs)} tools to {group_path}")

    master_lines = [
        f"# Auto-generated master module for AITBC CLI MCP wrappers ({args.mode} mode).",
        "# This file imports all group-specific modules produced by",
        "# scripts/dev/generate_mcp_cli_tools.py --split-by-group.",
        "# Do not edit manually; regenerate instead.",
        "",
        "from __future__ import annotations",
        "",
    ]
    for module in group_modules:
        master_lines.append(f"import {module}  # noqa: F401")

    master_output = "\n".join(master_lines) + "\n"

    if args.check:
        if not out_path.exists() or out_path.read_text() != master_output:
            print(f"Generated master module would change: {out_path}")
            return 1
        print("All generated modules are up to date.")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(master_output)
    print(f"Wrote master imports for {len(group_modules)} groups to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
