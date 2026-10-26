"""Parity test: generated MCP CLI tool schemas vs the aitbc Click command tree.

For every leaf command the generator wraps (``--mode all --split-by-group``),
the committed ``mcp-server/aitbc_mcp_cli_tools_generated*.py`` modules must
expose a tool whose option forwarding covers every non-excluded CLI flag —
including the *negative* spelling of dual ``--x``/``--no-x`` flag pairs — and
must not forward a flag the command does not declare (leaf or hoisted
top-level group option).

The generated sources are parsed with ``ast`` so the test gates the shipped
schemas, not just the generator's in-memory spec. Exclusion policy
(password/secret skips, path-scoped skips, hidden options, --format/--output
dedup) is taken from the generator module so an intentional skip never fails
here — the test only fails on *unexplained* drift.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_SERVER_DIR = REPO_ROOT / "mcp-server"
GENERATOR_PATH = REPO_ROOT / "scripts" / "dev" / "generate_mcp_cli_tools.py"

sys.path.insert(0, str(REPO_ROOT / "cli"))

import click  # noqa: E402


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_mcp_cli_tools", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()

RESERVED_PARAMS = {"role", "host", "timeout", "dry_run", "confirm"}


def _literal_map(node: ast.AST) -> dict[str, object]:
    """Evaluate a ``{str: str}`` or ``{str: (str, str)}`` dict literal."""
    if not isinstance(node, ast.Dict):
        return {}
    out: dict[str, object] = {}
    for key, value in zip(node.keys, node.values, strict=True):
        if not isinstance(key, ast.Constant):
            continue
        if isinstance(value, ast.Constant):
            out[str(key.value)] = value.value
        elif isinstance(value, ast.Tuple) and all(isinstance(e, ast.Constant) for e in value.elts):
            out[str(key.value)] = tuple(e.value for e in value.elts)
    return out


def _emitted_tools() -> dict[str, dict[str, object]]:
    """Parse every generated module; return func-name -> emitted flag data."""
    tools: dict[str, dict[str, object]] = {}
    for path in sorted(MCP_SERVER_DIR.glob("aitbc_mcp_cli_tools_generated*.py")):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            params = [a.arg for a in node.args.args]
            emitted: set[str] = set()
            neg_emitted: set[str] = set()
            for stmt in ast.walk(node):
                if not (isinstance(stmt, ast.Call) and getattr(stmt.func, "id", "") == "_collect_options"):
                    continue
                for kw in stmt.keywords:
                    if kw.arg in ("flags", "values"):
                        emitted.update(str(v) for v in _literal_map(kw.value).values())
                    elif kw.arg == "dual_flags":
                        for pair in _literal_map(kw.value).values():
                            if isinstance(pair, tuple):
                                emitted.add(str(pair[0]))
                                neg_emitted.add(str(pair[1]))
            tools[node.name] = {
                "params": params,
                "flags": emitted,
                "neg_flags": neg_emitted,
            }
    return tools


def _expected_flags(gen, path: tuple[str, ...], cmd: click.Command):
    """Compute expected (flag, neg-flag) coverage straight from Click params.

    Returns (expected, real) where ``expected`` maps each emitted flag to its
    required secondary spelling (or None) and ``real`` is the set of all long
    flags the command line genuinely accepts (leaf + hoisted top group,
    including secondary spellings).
    """
    path_skips = gen.SKIP_OPTIONS_BY_PATH.get(path, frozenset())
    chosen = gen._choose_format_options(cmd)
    leaf_flags: set[str] = set()
    expected: dict[str, str | None] = {}
    real: set[str] = set()

    def consider(param: click.Option) -> None:
        for opt in list(param.opts) + list(param.secondary_opts or []):
            if opt.startswith("--"):
                real.add(opt.lstrip("-"))

    for param in cmd.params:
        if not isinstance(param, click.Option):
            continue
        consider(param)
        if chosen.get(param.name or "") is not param:
            continue
        if (param.name or "").replace("-", "_") in path_skips:
            continue
        if gen.is_excluded_option(param):
            continue
        flag = gen.get_flag_name(param)
        if not flag:
            continue
        secondary = [o.lstrip("-") for o in (param.secondary_opts or []) if o.startswith("--")]
        leaf_flags.add(flag)
        expected[flag] = secondary[0] if secondary else None

    top_group = gen.cli.commands.get(path[0]) if len(path) >= 2 else None
    if isinstance(top_group, click.Group):
        for param in top_group.params:
            if not isinstance(param, click.Option):
                continue
            consider(param)
            flag = gen.get_flag_name(param)
            if not flag or flag in leaf_flags:
                continue
            if gen.is_excluded_option(param):
                continue
            secondary = [o.lstrip("-") for o in (param.secondary_opts or []) if o.startswith("--")]
            expected[flag] = secondary[0] if secondary else None

    return expected, real


def _leaf_commands():
    for result in gen.walk_commands(gen.cli):
        path = tuple(result["path"])
        if not path or isinstance(result["command"], click.Group):
            continue
        yield path, result["command"]


def test_all_cli_options_reachable_in_generated_tools():
    """Every non-excluded CLI flag must be forwarded by its generated tool."""
    tools = _emitted_tools()
    existing = gen.existing_tool_names()
    failures: list[str] = []
    covered = 0
    for path, cmd in _leaf_commands():
        if path in gen.FORCE_SKIP_PATHS or gen.path_to_func_name(path) in existing:
            continue
        tool = tools.get(gen.path_to_func_name(path))
        if tool is None:
            failures.append(f"missing tool for `aitbc {' '.join(path)}`")
            continue
        expected, _real = _expected_flags(gen, path, cmd)
        for flag, neg in expected.items():
            if flag not in tool["flags"]:
                failures.append(f"aitbc {' '.join(path)}: --{flag} not forwarded by {gen.path_to_func_name(path)}")
            elif neg is not None and neg not in tool["neg_flags"]:
                failures.append(
                    f"aitbc {' '.join(path)}: --{neg} (negative of --{flag}) unreachable in {gen.path_to_func_name(path)}"
                )
        covered += 1
    assert covered > 400, "sanity: the parity sweep should cover hundreds of tools"
    assert not failures, "CLI options missing from generated MCP tool schemas:\n" + "\n".join(failures)


def test_generated_tools_forward_only_real_flags():
    """No generated tool may emit a flag the command does not declare."""
    tools = _emitted_tools()
    existing = gen.existing_tool_names()
    failures: list[str] = []
    for path, cmd in _leaf_commands():
        if path in gen.FORCE_SKIP_PATHS or gen.path_to_func_name(path) in existing:
            continue
        tool = tools.get(gen.path_to_func_name(path))
        if tool is None:
            continue
        _expected, real = _expected_flags(gen, path, cmd)
        for flag in tool["flags"] | tool["neg_flags"]:
            if flag not in real:
                failures.append(f"{gen.path_to_func_name(path)} emits --{flag} but `aitbc {' '.join(path)}` has no such flag")
    assert not failures, "Generated MCP tools emit flags the CLI does not declare:\n" + "\n".join(failures)


def test_dual_flag_parameters_are_tri_state():
    """A dual ``--x``/``--no-x`` parameter must be an optional bool (tri-state)."""
    tools = _emitted_tools()
    failures: list[str] = []
    for path, cmd in _leaf_commands():
        func_name = gen.path_to_func_name(path)
        tool = tools.get(func_name)
        if tool is None:
            continue
        path_skips = gen.SKIP_OPTIONS_BY_PATH.get(path, frozenset())
        chosen = gen._choose_format_options(cmd)
        for param in cmd.params:
            if not isinstance(param, click.Option) or not getattr(param, "secondary_opts", None):
                continue
            if chosen.get(param.name or "") is not param:
                continue
            if (param.name or "").replace("-", "_") in path_skips:
                continue
            if gen.is_excluded_option(param):
                continue
            base = (param.name or "").replace("-", "_")
            # The emitted python name may carry a dedup/reserved suffix; any
            # parameter whose docstring name starts with the base qualifies.
            if not any(p == base or p.startswith(base + "_") for p in tool["params"]):
                failures.append(f"{func_name}: dual-flag --{param.opts[0].lstrip('-')} has no parameter")
    assert not failures, "\n".join(failures)
