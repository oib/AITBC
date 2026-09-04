#!/usr/bin/env python3
"""Dump AITBC MCP tool names + descriptions to a file for context loading.

Uses the AITBC MCP server module directly so it can inspect each tool's
implementation and infer the underlying AITBC CLI group / HTTP service.  The
``--role`` filter then classifies tools by the node roles that typically use
that group or service.

Examples
--------
    scripts/dump_mcp_tools.py
    scripts/dump_mcp_tools.py --role shop --output mcp-tools-shop.md
    scripts/dump_mcp_tools.py --role hub --read-only --output mcp-tools-hub.md
    scripts/dump_mcp_tools.py --role shop --include-generic --output mcp-tools-shop.md
    scripts/dump_mcp_tools.py --filter "wallet" --format json
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Make the canonical repo and mcp-server modules importable.
PROJECT_ROOT = "/opt/aitbc"
MCP_SERVER_DIR = "/opt/aitbc/mcp-server"
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, MCP_SERVER_DIR)

os.environ.setdefault("AITBC_MCP_LOG_LEVEL", "WARNING")

import aitbc_mcp_server as _server  # noqa: E402

ALL_ROLES = ["hub", "customer", "shop", "follower", "customer2", "follower2"]

# Maps extracted tags (CLI group, CLI group:subcommand, or HTTP service / path
# domain) to the node roles that typically run the relevant service.  Tags not
# in this map are treated as available on all roles (e.g. base services like
# blockchain-rpc, node, system, etc.).
ROLE_HINTS: dict[str, list[str]] = {
    # CLI groups
    "ai": ["hub", "customer", "customer2"],
    "market": ["hub", "customer", "shop"],
    "marketplace": ["hub", "customer", "shop"],
    "wallet": ["hub", "customer", "customer2"],
    "transactions": ["hub", "customer", "customer2"],
    "dashboard:customer": ["hub", "customer", "customer2"],
    "dashboard:shop": ["shop", "follower", "follower2"],
    "gpu": ["shop", "follower", "follower2"],
    "gpu-onchain": ["shop", "follower", "follower2"],
    "pool-hub": ["shop", "follower", "follower2"],
    "mining": ["shop", "follower", "follower2"],
    "edge": ["shop", "follower", "follower2"],
    "whisper": ["shop", "follower", "follower2"],
    "ffmpeg": ["shop", "follower", "follower2"],
    "hermes": ["shop", "follower", "follower2"],
    "ollama": ["shop", "follower", "follower2"],
    "exchange-island": ["hub", "customer"],
    "ipfs:rentals": ["hub", "customer", "shop"],
    "liquidity": ["hub", "customer", "customer2"],
    "developer": ["hub"],
    "confidential": ["hub", "customer"],
    "tee": ["hub", "customer"],
    "zk": ["hub", "customer"],
    "bridge": ["hub", "shop"],
    "crosschain": ["hub", "shop"],
    "cross-chain": ["hub", "shop"],
    "islands": ["hub", "customer"],
    # HTTP services / path domains
    "coordinator-api": ["hub", "shop"],
    "api-gateway": ["hub"],
    "agent-coordinator": ["hub"],
    "blockchain-event-bridge": ["hub"],
    "exchange": ["hub", "customer"],
    # marketplace, gpu, pool-hub, whisper, ffmpeg, hermes, ollama are already
    # covered by the identical CLI-group entries above.
    "blockchain-explorer": ["hub", "shop", "follower", "follower2"],
    "ipfs": ["hub", "customer", "customer2", "shop", "follower", "follower2"],
}


def _port_to_service() -> dict[str, str]:
    """Build a port -> service map from the server's ALL_SERVICE_BASES."""
    port_map: dict[str, str] = {}
    for service, base in _server.ALL_SERVICE_BASES.items():
        m = re.search(r":(\d+)", base)
        if m:
            port_map[m.group(1)] = service
    return port_map


_PORT_MAP = _port_to_service()


def _path_tag(path: str) -> str | None:
    """Turn an HTTP path like 'v1/zk/health' or 'gpu/allocate' into a tag."""
    if not path:
        return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    first = parts[0]
    if re.match(r"^v\d+$", first) and len(parts) > 1:
        first = parts[1]
    # Skip very generic path segments.
    if first in {
        "info",
        "health",
        "status",
        "head",
        "mempool",
        "blocks",
        "block",
        "account",
        "transaction",
        "balance",
        "staking",
        "bond",
        "islands",
        "chains",
        "consensus",
        "validators",
        "genesis_allocations",
        "delta",
        "snapshot",
        "rates",
        "pools",
    }:
        return None
    return first


def _shorten_params(input_schema: dict) -> str:
    """Return a compact summary of required/optional parameters."""
    props = input_schema.get("properties", {})
    if not props:
        return "no args"
    required = set(input_schema.get("required", []))
    parts = []
    for name, meta in props.items():
        info = name
        if name in required:
            info = f"{info}*"
        types = meta.get("type")
        if isinstance(types, list):
            info = f"{info}: {'|'.join(types)}"
        elif types:
            info = f"{info}: {types}"
        parts.append(info)
    return ", ".join(parts)


def _tool_source(fn: Any, seen: set[int] | None = None) -> str:
    """Return a tool's source, plus the source of any local mcp-server helpers it calls."""
    if seen is None:
        seen = set()
    fid = id(fn)
    if fid in seen:
        return ""
    seen.add(fid)

    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        return ""

    extra = ""
    module = fn.__module__ if inspect.isfunction(fn) else None
    if not module:
        return src

    for name in fn.__code__.co_names:
        obj = fn.__globals__.get(name)
        if not inspect.isfunction(obj):
            continue
        # Expand helpers from the mcp-server directory, but not the main server
        # module itself (its body contains ALL_SERVICE_BASES etc. which would
        # introduce false-positive ports and service names).
        if obj.__module__ == "aitbc_mcp_server":
            continue
        mod = sys.modules.get(obj.__module__)
        if mod and mod.__file__ and mod.__file__.startswith(MCP_SERVER_DIR):
            extra += _tool_source(obj, seen)

    return src + extra


def _extract_tags(src: str) -> list[str]:
    """Parse source and return CLI group / service / path-domain tags."""
    tags: list[str] = []

    # _aitbc_cli_read_tool(role, host, "group", "subcommand"?)
    for m in re.finditer(
        r"_aitbc_cli_read_tool\s*\(\s*role\s*,\s*host\s*,\s*['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?",
        src,
    ):
        group = m.group(1)
        subcommand = m.group(2)
        tags.append(group)
        if subcommand:
            tags.append(f"{group}:{subcommand}")

    # _run_aitbc_cli_write(role, host, "group", ...)
    for m in re.finditer(
        r"_run_aitbc_cli_write\s*\(\s*role\s*,\s*host\s*,\s*['\"]([^'\"]+)['\"]",
        src,
    ):
        tags.append(m.group(1))

    # _run_aitbc_cli(target, "group", ...)
    for m in re.finditer(
        r"_run_aitbc_cli\s*\(\s*target\s*,\s*['\"]([^'\"]+)['\"]",
        src,
    ):
        tags.append(m.group(1))

    # _build_aitbc_cli_command("group", ...)
    for m in re.finditer(
        r"_build_aitbc_cli_command\s*\(\s*['\"]([^'\"]+)['\"]",
        src,
    ):
        tags.append(m.group(1))

    # _http_read_tool / _http_write_tool(role, host, "service", "path", ...)
    for m in re.finditer(
        r"_http_(?:read|write)_tool\s*\(\s*role\s*,\s*host\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]",
        src,
    ):
        tags.append(m.group(1))
        pt = _path_tag(m.group(2))
        if pt:
            tags.append(pt)

    # _run_http(target, "service", "path", ...) -- path may be a quoted literal
    for m in re.finditer(
        r"_run_http\s*\(\s*target\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]",
        src,
    ):
        tags.append(m.group(1))
        pt = _path_tag(m.group(2))
        if pt:
            tags.append(pt)

    # _run_http(target, "service", <variable path>, ...)  -- still useful for service
    for m in re.finditer(
        r"_run_http\s*\(\s*target\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*[^'\"\s,)]+",
        src,
    ):
        tags.append(m.group(1))

    # _call_liquidity(role, host, "path")
    for m in re.finditer(
        r"_call_liquidity\s*\(\s*role\s*,\s*host\s*,\s*['\"]([^'\"]+)['\"]",
        src,
    ):
        pt = _path_tag(m.group(1))
        if pt:
            tags.append(pt)

    # _call_zk(role, host, "path", ...)
    for m in re.finditer(
        r"_call_zk\s*\(\s*role\s*,\s*host\s*,\s*['\"]([^'\"]+)['\"]",
        src,
    ):
        pt = _path_tag(m.group(1))
        if pt:
            tags.append(pt)

    # Fixed curl commands with localhost:PORT -> map to service.
    for m in re.finditer(r"curl\s+[^'\"\n]*http://localhost:(\d+)", src):
        service = _PORT_MAP.get(m.group(1))
        if service:
            tags.append(service)

    return list(dict.fromkeys(tags))


def _roles_for_tags(tags: list[str]) -> list[str]:
    """Map extracted tags to node roles. Unknown tags default to all roles."""
    roles: set[str] = set()
    explicit = False
    for tag in tags:
        if tag in ROLE_HINTS:
            roles.update(ROLE_HINTS[tag])
            explicit = True
        elif ":" in tag:
            group = tag.split(":", 1)[0]
            if group in ROLE_HINTS:
                roles.update(ROLE_HINTS[group])
                explicit = True

    if not explicit:
        return ALL_ROLES.copy()

    return sorted(roles & set(ALL_ROLES))


def _build_tools() -> list[dict[str, Any]]:
    """Load tools from the aitbc MCP server and classify each one."""
    tools = []
    for name in sorted(_server.mcp._tool_manager._tools):
        tool = _server.mcp._tool_manager._tools[name]
        src = _tool_source(tool.fn)
        tags = _extract_tags(src)
        roles = _roles_for_tags(tags)
        tools.append(
            {
                "name": name,
                "description": tool.description,
                "read_only": tool.annotations.read_only_hint if tool.annotations else None,
                "destructive": tool.annotations.destructive_hint if tool.annotations else None,
                "args": _shorten_params(tool.parameters),
                "tags": tags,
                "roles": roles,
            }
        )
    return tools


def _filter_tools(
    tools: list[dict[str, Any]],
    role: str | None,
    filter_: str | None,
    read_only: bool,
    destructive: bool,
    include_generic: bool,
) -> list[dict[str, Any]]:
    if role:
        role_lower = role.lower()

        def _role_match(t: dict[str, Any]) -> bool:
            if role_lower not in t["roles"]:
                return False
            if t["roles"] == ALL_ROLES:
                return include_generic
            return True

        tools = [t for t in tools if _role_match(t)]

    if filter_:
        pat = re.compile(filter_, re.IGNORECASE)
        tools = [
            t
            for t in tools
            if pat.search(t["name"])
            or pat.search(t["description"])
            or any(pat.search(tag) for tag in t["tags"])
        ]

    if read_only:
        tools = [t for t in tools if t["read_only"]]
    if destructive:
        tools = [t for t in tools if t["destructive"]]

    return tools


def _render(tools: list[dict[str, Any]], format_: str) -> str:
    if format_ == "json":
        return json.dumps(tools, indent=2)

    lines = ["# AITBC MCP tools reference", "", f"Total: {len(tools)} tools", ""]
    for t in tools:
        hint = ""
        if t.get("read_only"):
            hint = " (read-only)"
        elif t.get("destructive"):
            hint = " (destructive)"
        lines.append(f"## {t['name']}{hint}")
        if t.get("description"):
            lines.append(t["description"])
        lines.append(f"Tags: {', '.join(t['tags'])}")
        lines.append(f"Roles: {', '.join(t['roles'])}")
        lines.append(f"Args: {t['args']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump AITBC MCP tool reference.")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file. Prints to stdout if omitted.",
    )
    parser.add_argument(
        "--role",
        type=str,
        default=None,
        choices=ALL_ROLES,
        help="Filter tools by the node role they are typically used with.",
    )
    parser.add_argument(
        "--include-generic",
        action="store_true",
        help="When --role is used, also include generic tools that work on all roles.",
    )
    parser.add_argument(
        "--filter",
        type=str,
        dest="filter_",
        default=None,
        help="Regex filter on tool name, description, or tags.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Only include read-only tools.",
    )
    parser.add_argument(
        "--destructive",
        action="store_true",
        help="Only include destructive tools.",
    )
    args = parser.parse_args()

    tools = _build_tools()
    tools = _filter_tools(
        tools,
        args.role,
        args.filter_,
        args.read_only,
        args.destructive,
        args.include_generic,
    )
    text = _render(tools, args.format)

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {len(text)} characters to {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
