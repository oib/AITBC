#!/usr/bin/env python3
"""Validate hand-written MCP tool dispatch literals against live surfaces.

``check-mcp-cli-drift.sh`` diffs the *generated* MCP modules against the CLI
tree, but the hand-written files (aitbc_mcp_server.py, aitbc_mcp_rpc_tools.py,
aitbc_mcp_cli_tools.py, aitbc_mcp_zk_tools.py, aitbc_mcp_liquidity_tools.py)
carry their own route and command literals that nothing checked — the stale
``cross-chain/swap`` (404), ``market offers`` (no such subcommand) and
``unpin --rental-id`` (dead options) bugs all lived there.

Two checks, both over the same extraction as
``scripts/dev/gen_mcp_tool_inventory.py``:

a. CLI literals — every ``(group, subcommand)`` pair a hand file passes to
   ``_aitbc_cli_read_tool`` / ``_run_aitbc_cli_write`` / ``_run_aitbc_cli``
   must resolve to a real command in the Click tree walked by
   ``scripts/docs/gen_cli_command_docs.py``. A dead literal fails.

b. HTTP literals — every service+path a hand file passes to
   ``_http_read_tool`` / ``_http_write_tool`` / ``_run_http`` (and the
   ``_call_zk`` / ``_call_liquidity`` wrappers) is matched against the
   FastAPI routers: ``apps/blockchain-node/src/aitbc_chain/rpc/**`` for
   ``blockchain-rpc`` (via gen_doc_mesh.parse_routes) and
   ``apps/<service>/**/*.py`` router files for the rest. Unmatched literals
   are warnings when the service has no discoverable route set or the path
   is too dynamic to compare, dead (exit 1) when a route set exists and
   nothing matches.

Exit 0 when no dead literal is found; prints dead tool + literal + file.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))
sys.path.insert(0, str(REPO / "scripts" / "docs"))

import gen_mcp_tool_inventory as inv  # noqa: E402

GENERATED_PREFIX = inv.GENERATED_PREFIX


@dataclass
class Verdict:
    row: inv.ToolRow
    status: str  # "pass" | "warn" | "fail"
    detail: str = ""


@dataclass
class Report:
    verdicts: list[Verdict] = field(default_factory=list)

    def add(self, row: inv.ToolRow, status: str, detail: str = "") -> None:
        self.verdicts.append(Verdict(row, status, detail))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.verdicts:
            out[v.status] = out.get(v.status, 0) + 1
        return out


# ---------------------------------------------------------------------------
# a. CLI tree
# ---------------------------------------------------------------------------


def cli_command_paths() -> tuple[set[tuple[str, ...]], set[tuple[str, ...]]]:
    """(leaf command paths, group paths) of the live Click tree."""
    import gen_cli_command_docs as gcd

    leaves = {tuple(p) for p, _ in gcd.iter_commands()}
    groups: set[tuple[str, ...]] = set()

    def walk(cmd, path):
        import click

        if isinstance(cmd, click.Group):
            groups.add(path)
            for name in cmd.commands:
                walk(cmd.commands[name], path + (name,))

    for top in gcd.cli.commands:
        walk(gcd.cli.commands[top], (top,))
    return leaves, groups


def check_cli(row: inv.ToolRow, leaves: set, groups: set) -> str:
    """'' when the (group, sub) literal resolves, else a reason string."""
    if not row.group:
        return "non-literal group" if not row.sub_dynamic else ""
    if row.sub_dynamic:
        return ""  # dynamic subcommand — cannot resolve statically
    path = (row.group,) + row.sub
    if path in leaves or (not row.sub and (row.group,) in groups):
        return ""
    if (row.group,) not in leaves and (row.group,) not in groups:
        return f"unknown aitbc group '{row.group}'"
    return f"no command 'aitbc {' '.join(path)}'"


# ---------------------------------------------------------------------------
# b. HTTP routes
# ---------------------------------------------------------------------------

# @app.get / @router.get both appear; empty path ("") is legal — prefix-only
# routes like @router.get("") on APIRouter(prefix="/contracts") serve the
# literal "contracts", so the capture is `*` not `+`.
_ROUTE_DEC = re.compile(r'@(\w+)\.(get|post|put|delete|patch|websocket)\(\s*"([^"]*)"')
_ROUTER_DEF = re.compile(r'(\w+)\s*=\s*\w*APIRouter\(\s*prefix="([^"]*)"')
_MOUNT = re.compile(r'include_router\(\s*\w+\s*,\s*prefix="([^"]+)"')


def _service_root(service: str) -> Path | None:
    if service == "blockchain-rpc":
        return REPO / "apps" / "blockchain-node" / "src" / "aitbc_chain" / "rpc"
    apps = REPO / "apps"
    if (apps / service).is_dir():
        return apps / service
    for cand in sorted(apps.iterdir()):
        if cand.is_dir() and cand.name.startswith(service):
            return cand
    return None


def app_route_paths(service: str) -> set[str]:
    """All plausible full route paths a service exposes (prefix × decorator)."""
    root = _service_root(service)
    if root is None:
        return set()
    mounts = [""]
    file_routes: set[str] = set()
    for py in sorted(root.rglob("*.py")):
        text = py.read_text(errors="replace")
        mounts += _MOUNT.findall(text)
        prefixes = dict(_ROUTER_DEF.findall(text))
        for var, _method, path in _ROUTE_DEC.findall(text):
            candidates = {path}
            if var in prefixes:
                candidates.add(prefixes[var] + path)
            file_routes |= candidates
    full = {p.lstrip("/") for p in file_routes}
    for mount in mounts:
        full |= {(mount.rstrip("/") + "/" + p.lstrip("/")).lstrip("/") for p in file_routes}
    return {p.strip("/") for p in full if p.strip("/")}


def rpc_route_paths() -> set[str]:
    """blockchain-rpc route paths: router scan + gen_doc_mesh.parse_routes."""
    import gen_doc_mesh

    return app_route_paths("blockchain-rpc") | {r.path[len("/rpc/") :] for r in gen_doc_mesh.parse_routes(set())}


def _seg_match(literal: str, route: str) -> bool:
    a = [s for s in literal.split("/") if s]
    b = [s for s in route.split("/") if s]
    if len(a) != len(b):
        return False

    def same(x: str, y: str) -> bool:
        return x == y or (x.startswith("{") and x.endswith("}")) or (y.startswith("{") and y.endswith("}"))

    return all(same(x, y) for x, y in zip(a, b, strict=True))


def http_matches(literal: str, routes: set[str]) -> bool:
    lit = literal.split("?", 1)[0].strip("/")
    return any(_seg_match(lit, r) for r in routes)


def route_set(service: str, rpc_routes: set[str], cache: dict[str, set[str]]) -> set[str]:
    if service == "blockchain-rpc":
        return rpc_routes
    if service not in cache:
        cache[service] = app_route_paths(service)
    return cache[service]


def check_http(row: inv.ToolRow, rpc_routes: set[str], cache: dict) -> tuple[str, str]:
    """(status, detail) for an rpc-kind row."""
    if not row.service:
        return "warn", "non-literal service"
    if not row.path:
        return "warn", "non-literal path"
    routes = route_set(row.service, rpc_routes, cache)
    if not routes:
        return "warn", f"no routes discovered for service '{row.service}'"
    first_seg = row.path.split("/", 1)[0]
    if first_seg.startswith("{"):
        return "warn", "leading dynamic segment"
    if http_matches(row.path, routes):
        return "pass", ""
    return "fail", f"no {row.service} route matches '{row.path}'"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    rows = [r for r in inv.iter_tool_rows() if not r.file.endswith(GENERATED_PREFIX + ".py")]
    rows = [r for r in rows if GENERATED_PREFIX not in Path(r.file).name]
    rep = Report()

    leaves, groups = cli_command_paths()
    rpc_routes = rpc_route_paths()
    cache: dict[str, set[str]] = {}

    for row in rows:
        if row.kind == "cli":
            reason = check_cli(row, leaves, groups)
            rep.add(row, "fail" if reason else "pass", reason)
        elif row.kind == "rpc":
            status, detail = check_http(row, rpc_routes, cache)
            rep.add(row, status, detail)

    for v in rep.verdicts:
        if v.status == "fail":
            print(f"DEAD  {v.row.tool}  {v.row.literal}  ({v.row.file}) — {v.detail}")
        elif v.status == "warn":
            print(f"warn  {v.row.tool}  {v.row.literal}  ({v.row.file}) — {v.detail}")

    c = rep.counts()
    print(
        f"\nhand-file literals checked: {len(rep.verdicts)} "
        f"(pass={c.get('pass', 0)} warn={c.get('warn', 0)} fail={c.get('fail', 0)})"
    )
    return 1 if c.get("fail") else 0


if __name__ == "__main__":
    raise SystemExit(main())
