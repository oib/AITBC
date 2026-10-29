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
from typing import Any
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


def _function_emissions(node: ast.FunctionDef) -> tuple[set[str], set[str]]:
    """Walk one generated function body; return (flags, neg-flags) emitted."""
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
    return emitted, neg_emitted


def _emitted_tools() -> dict[str, dict[str, object]]:
    """Parse every generated module; return func-name -> emitted flag data."""
    tools: dict[str, dict[str, object]] = {}
    for path in sorted(MCP_SERVER_DIR.glob("aitbc_mcp_cli_tools_generated*.py")):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            emitted, neg_emitted = _function_emissions(node)
            tools[node.name] = {
                "params": [a.arg for a in node.args.args],
                "flags": emitted,
                "neg_flags": neg_emitted,
            }
    return tools


def _secondary_name(param: click.Option) -> str | None:
    secondary = [o.lstrip("-") for o in (param.secondary_opts or []) if o.startswith("--")]
    return secondary[0] if secondary else None


def _real_flag_names(param: click.Option) -> set[str]:
    return {o.lstrip("-") for o in list(param.opts) + list(param.secondary_opts or []) if o.startswith("--")}


def _leaf_expected(gen, path, cmd, path_skips, chosen):
    """Walk the leaf command's params; return (expected, leaf_flags, real)."""
    expected: dict[str, str | None] = {}
    leaf_flags: set[str] = set()
    real: set[str] = set()
    for param in cmd.params:
        if not isinstance(param, click.Option):
            continue
        real.update(_real_flag_names(param))
        if chosen.get(param.name or "") is not param:
            continue
        if (param.name or "").replace("-", "_") in path_skips:
            continue
        if gen.is_excluded_option(param):
            continue
        flag = gen.get_flag_name(param)
        if flag:
            leaf_flags.add(flag)
            expected[flag] = _secondary_name(param)
    return expected, leaf_flags, real


def _group_expected(gen, path, leaf_flags):
    """Walk the top group's hoisted params; return (expected, real)."""
    expected: dict[str, str | None] = {}
    real: set[str] = set()
    top_group = gen.cli.commands.get(path[0]) if len(path) >= 2 else None
    if not isinstance(top_group, click.Group):
        return expected, real
    for param in top_group.params:
        if not isinstance(param, click.Option):
            continue
        real.update(_real_flag_names(param))
        flag = gen.get_flag_name(param)
        if not flag or flag in leaf_flags or gen.is_excluded_option(param):
            continue
        expected[flag] = _secondary_name(param)
    return expected, real


def _expected_flags(gen, path: tuple[str, ...], cmd: click.Command):
    """Compute expected (flag, neg-flag) coverage straight from Click params."""
    path_skips = gen.SKIP_OPTIONS_BY_PATH.get(path, frozenset())
    chosen = gen._choose_format_options(cmd)
    expected, leaf_flags, real = _leaf_expected(gen, path, cmd, path_skips, chosen)
    g_expected, g_real = _group_expected(gen, path, leaf_flags)
    expected.update(g_expected)
    real.update(g_real)
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


# ---------------------------------------------------------------------------
# Hand-maintained module: aitbc_mcp_cli_tools.py
#
# The hand file wraps calls differently from the generated modules: instead of
# ``_collect_options`` it passes ``(role, host, group, subcommand, args,
# options, ...)`` positionally to ``_aitbc_cli_read_tool`` /
# ``_run_aitbc_cli_write`` and builds option dicts via literals and
# ``options["flag"] = ...`` assignments.  The checks below parse the same
# literals and validate them against the Click tree: every emitted
# (group, subcommand) path must resolve to a real command, and every forwarded
# flag name must be a real option on the leaf (``options`` /
# ``subcommand_options``) or on the first-level group (``group_options``).
# ---------------------------------------------------------------------------

HAND_PATH = MCP_SERVER_DIR / "aitbc_mcp_cli_tools.py"
HAND_WRAPPERS = {"_aitbc_cli_read_tool", "_run_aitbc_cli_write"}
_OPTION_DICT_NAMES = {"options", "group_options", "subcommand_options"}


def _str_constant(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _token_list(node: ast.AST | None) -> list[str] | None:
    """Literal ``str`` / ``list[str]`` / ``None`` → token list; else None."""
    if node is None or (isinstance(node, ast.Constant) and node.value is None):
        return []
    s = _str_constant(node)
    if s is not None:
        import shlex

        return shlex.split(s)
    if isinstance(node, (ast.List, ast.Tuple)):
        out: list[str] = []
        for elt in node.elts:
            v = _str_constant(elt)
            if v is None:
                return None
            out.append(v)
        return out
    return None


def _dict_keys(node: ast.AST) -> set[str]:
    """Constant string keys of a dict literal."""
    if not isinstance(node, ast.Dict):
        return set()
    keys: set[str] = set()
    for k in node.keys:
        v = _str_constant(k)
        if v is not None:
            keys.add(v)
    return keys


def _call_arg(call: ast.Call, index: int, name: str) -> ast.AST | None:
    """Positional-or-keyword argument of a call, keyword wins."""
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    if len(call.args) > index:
        return call.args[index]
    return None


def _func_option_literals(node: ast.FunctionDef) -> dict[str, set[str]]:
    """All flag names each option-dict variable can carry in one function.

    Collects keys from ``X = {...}`` / ``X: t = {...}`` assignments and
    ``X["flag"] = ...`` subscript writes for X in _OPTION_DICT_NAMES.  A key
    set to ``None``/``True`` renders as a bare ``--flag``; any other value as
    ``--flag=value`` — both are forwarded flags either way.
    """
    keys: dict[str, set[str]] = {name: set() for name in _OPTION_DICT_NAMES}
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Assign):
            if isinstance(stmt.value, ast.Dict):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.id in keys:
                        keys[tgt.id] |= _dict_keys(stmt.value)
            for tgt in stmt.targets:
                if (
                    isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id in keys
                    and isinstance(tgt.slice, ast.Constant)
                ):
                    keys[tgt.value.id].add(str(tgt.slice.value))
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.value, ast.Dict):
            if isinstance(stmt.target, ast.Name) and stmt.target.id in keys:
                keys[stmt.target.id] |= _dict_keys(stmt.value)
    return keys


def _hand_emissions() -> list[dict[str, Any]]:
    """Parse the hand file; one record per literal ``aitbc`` wrapper call."""
    out: list[dict[str, Any]] = []
    tree = ast.parse(HAND_PATH.read_text())
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        var_keys = _func_option_literals(node)
        for stmt in ast.walk(node):
            if not (isinstance(stmt, ast.Call) and getattr(stmt.func, "id", "") in HAND_WRAPPERS):
                continue
            group = _str_constant(_call_arg(stmt, 2, "group"))
            if group is None:
                continue  # non-literal group (helper internals) — nothing to check
            sub_tokens = _token_list(_call_arg(stmt, 3, "subcommand"))
            arg_tokens = _token_list(_call_arg(stmt, 4, "args"))

            def keys_for(node_value: ast.AST | None, var_keys: dict[str, set[str]] = var_keys) -> set[str]:
                if isinstance(node_value, ast.Dict):
                    return _dict_keys(node_value)
                if isinstance(node_value, ast.Name) and node_value.id in var_keys:
                    return var_keys[node_value.id]
                return set()

            # ``options`` is the only positional dict (index 5); group_options /
            # subcommand_options are keyword-only in both helpers.
            leaf_flags = keys_for(_call_arg(stmt, 5, "options")) | keys_for(_call_arg(stmt, 99, "subcommand_options"))
            group_flags = keys_for(_call_arg(stmt, 99, "group_options"))
            out.append(
                {
                    "tool": node.name,
                    "group": group,
                    "sub_tokens": sub_tokens,
                    "arg_tokens": arg_tokens,
                    "leaf_flags": leaf_flags,
                    "group_flags": group_flags,
                }
            )
    return out


def _resolve_leaf(group: str, tokens: list[str] | None) -> tuple[click.Command | None, str | None]:
    """Walk ``aitbc <group> <tokens...>`` down the Click tree.

    Returns (command, error): command is the deepest resolvable node (a leaf
    unless tokens ran out on a group).  Literal leading ``args`` tokens can
    continue the path because Click consumes them as subcommand names.
    """
    if tokens is None:
        return None, f"non-literal subcommand under group {group!r}"
    top = gen.cli.commands.get(group)
    if top is None:
        return None, f"unknown aitbc group {group!r}"
    node: click.Command = top
    for tok in tokens:
        if not isinstance(node, click.Group):
            break
        nxt = node.commands.get(tok)
        if nxt is None:
            break
        node = nxt
    return node, None


def _real_flags(cmd: click.Command) -> set[str]:
    return {n for p in cmd.params if isinstance(p, click.Option) for n in _real_flag_names(p)}


def test_hand_written_tools_resolve_to_click_commands():
    """Every literal (group, subcommand) in aitbc_mcp_cli_tools.py must resolve."""
    emissions = _hand_emissions()
    assert len(emissions) > 40, "sanity: the hand file wraps dozens of CLI calls"
    failures: list[str] = []
    for e in emissions:
        tokens = list(e["sub_tokens"] or []) + list(e["arg_tokens"] or [])
        cmd, err = _resolve_leaf(e["group"], tokens)
        path = f"aitbc {e['group']} {' '.join(tokens)}".rstrip()
        if err:
            failures.append(f"{e['tool']}: {err} ({path})")
        elif cmd is None or isinstance(cmd, click.Group):
            failures.append(f"{e['tool']}: `{path}` does not resolve to a leaf command")
    assert not failures, "Stale command paths in aitbc_mcp_cli_tools.py:\n" + "\n".join(failures)


def test_hand_written_tools_forward_only_real_flags():
    """Flags emitted by the hand file must exist on the resolved command."""
    failures: list[str] = []
    for e in _hand_emissions():
        tokens = list(e["sub_tokens"] or []) + list(e["arg_tokens"] or [])
        cmd, err = _resolve_leaf(e["group"], tokens)
        if err or cmd is None or isinstance(cmd, click.Group):
            continue  # path failures are reported by the resolver test
        path = f"aitbc {e['group']} {' '.join(tokens)}".rstrip()
        leaf_real = _real_flags(cmd)
        top = gen.cli.commands.get(e["group"])
        group_real = _real_flags(top) if isinstance(top, click.Group) else leaf_real
        for flag in sorted(e["leaf_flags"]):
            if flag not in leaf_real:
                failures.append(f"{e['tool']}: emits --{flag} but `{path}` has no such option")
        for flag in sorted(e["group_flags"]):
            if flag not in group_real:
                failures.append(f"{e['tool']}: emits group option --{flag} but `aitbc {e['group']}` has no such option")
    assert not failures, "aitbc_mcp_cli_tools.py emits flags the CLI does not declare:\n" + "\n".join(failures)


def _dual_flag_failures(func_name: str, tool: dict, params: list, eligible) -> list[str]:
    """Return failure strings for each eligible dual-flag param without a
    tool parameter (emitted name may carry a dedup/reserved suffix)."""
    out = []
    for param in params:
        if not eligible(param):
            continue
        base = (param.name or "").replace("-", "_")
        if not any(p == base or p.startswith(base + "_") for p in tool["params"]):
            out.append(f"{func_name}: dual-flag --{param.opts[0].lstrip('-')} has no parameter")
    return out


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

        def eligible(param, chosen=chosen, path_skips=path_skips) -> bool:
            if not isinstance(param, click.Option) or not getattr(param, "secondary_opts", None):
                return False
            if chosen.get(param.name or "") is not param:
                return False
            if (param.name or "").replace("-", "_") in path_skips:
                return False
            return not gen.is_excluded_option(param)

        failures.extend(_dual_flag_failures(func_name, tool, cmd.params, eligible))
    assert not failures, "\n".join(failures)
