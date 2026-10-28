"""EDGE-REG-CONSENSUS-1 guard: the RPC layer must not grow new write paths
against the v14 committed side-table set outside ``StateTransition.apply``.

The 2026-10-21 incident was an RPC handler (``POST /rpc/edge/register``)
writing a committed table on one node only — the aux root caught it at the
next block and the node stalled. v15 de-commits ``edge_node_registration``,
but the hazard pattern stays banned for every still-committed table: any new
``session.add``/``merge``/``delete``/ORM-mutation/raw-SQL write site in
``rpc/**`` that targets a v14-committed table must trip this test until it
is either removed or deliberately allow-listed here with a reason.

The allow-list pins the sites that exist today so this test also serves as
the audit trail: removing a hazard drops it from the list, and the test
fails if the list ever disagrees with the tree.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from aitbc_chain.state.side_root_shadow import COMMITTED_TABLES

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "apps" / "blockchain-node" / "src" / "aitbc_chain"
RPC_DIR = SRC / "rpc"
MODEL_FILES = (SRC / "base_models.py", SRC / "state" / "gpu_resources.py")

_MUTATORS = {"add", "merge", "delete", "add_all"}
_EXEC = {"execute", "exec"}
_DML_FUNCS = {"insert", "update", "delete"}
_RAW_SQL = re.compile(
    r"\b(?:insert(?:\s+or\s+\w+)?\s+into|update|delete\s+from|replace\s+into)\s+[`'\"\[]?(\w+)",
    re.IGNORECASE,
)


def _committed_model_classes() -> dict[str, str]:
    """Class name -> table name for every ORM class whose table is v14-committed."""
    out: dict[str, str] = {}
    for path in MODEL_FILES:
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in stmt.targets)
                    and isinstance(stmt.value, ast.Constant)
                    and stmt.value.value in COMMITTED_TABLES
                ):
                    out[node.name] = stmt.value.value
    return out


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _args_table(call: ast.Call, models: dict[str, str], bound: dict[str, str]) -> str | None:
    """Committed table a call's value derives from, or None."""
    fname = _call_name(call.func)
    if fname in models:  # x = Account(...)
        return models[fname]
    if not (isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)):
        return None
    if call.func.value.id in bound:  # x = <bound>.scalar_one_or_none()
        return bound[call.func.value.id]
    if fname not in {"get"} | _EXEC:
        return None
    for a in list(call.args) + [kw.value for kw in call.keywords]:
        for sub in ast.walk(a):
            if isinstance(sub, ast.Name) and sub.id in models:
                return models[sub.id]
    return None


def _bound_tables(tree: ast.AST, models: dict[str, str]) -> dict[str, str]:
    """var -> committed table for vars bound to a model instance or a
    select/get/execute result over one. Iterated to a fixpoint so two-hop
    bindings (``existing = result.scalar_one_or_none()``) resolve."""
    bound: dict[str, str] = {}
    for _ in range(4):
        changed = False
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
                continue
            table = _args_table(node.value, models, bound)
            for t in node.targets if table else ():
                if isinstance(t, ast.Name) and bound.get(t.id) != table:
                    bound[t.id] = table  # type: ignore[assignment]
                    changed = True
        if not changed:
            break
    return bound


def _mutator_sites(node: ast.Call, bound: dict[str, str], models: dict[str, str], rel: str) -> list:
    fname = _call_name(node.func)
    if fname not in _MUTATORS:
        return []
    out = []
    for a in node.args:
        t = bound.get(a.id) if isinstance(a, ast.Name) else None
        if t is None and isinstance(a, ast.Call):
            t = models.get(_call_name(a.func))
        # loop vars escape the binder — a var spelled exactly like a
        # committed table is flagged too
        # (``for account in new_accounts: session.add(account)``)
        if t is None and isinstance(a, ast.Name) and a.id in COMMITTED_TABLES:
            t = a.id
        if t:
            out.append((rel, node.lineno, t, f"session.{fname}"))
    return out


def _exec_sites(node: ast.Call, models: dict[str, str], rel: str) -> list:
    if _call_name(node.func) not in _EXEC:
        return []
    out = []
    for a in node.args:
        for sub in ast.walk(a):
            if not (isinstance(sub, ast.Call) and _call_name(sub.func) in _DML_FUNCS):
                continue
            for name in ast.walk(sub):
                if isinstance(name, ast.Name) and name.id in models:
                    out.append((rel, node.lineno, models[name.id], f"sql.{_call_name(sub.func)}"))
                    break
            break
    return out


def _assign_sites(node: ast.Assign, bound: dict[str, str], rel: str) -> list:
    return [
        (rel, node.lineno, bound[t.value.id], "attr-mutation")
        for t in node.targets
        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id in bound
    ]


def _const_sites(node: ast.Constant, rel: str) -> list:
    if not isinstance(node.value, str):
        return []
    return [
        (rel, node.lineno, m.group(1).lower(), "raw-sql")
        for m in _RAW_SQL.finditer(node.value)
        if m.group(1).lower() in COMMITTED_TABLES
    ]


def _scope_sites(scope: ast.AST, models: dict[str, str], rel: str) -> list:
    bound = _bound_tables(scope, models)
    sites: list[tuple[str, int, str, str]] = []
    for node in ast.walk(scope):
        if isinstance(node, ast.Call):
            sites += _mutator_sites(node, bound, models, rel)
            sites += _exec_sites(node, models, rel)
        elif isinstance(node, ast.Assign):
            sites += _assign_sites(node, bound, rel)
        elif isinstance(node, ast.Constant):
            sites += _const_sites(node, rel)
    return sites


def _scan_rpc() -> list[tuple[str, int, str, str]]:
    """Return (relpath, line, table, kind) write sites on committed tables."""
    models = _committed_model_classes()
    sites: list[tuple[str, int, str, str]] = []
    for path in sorted(RPC_DIR.rglob("*.py")):
        rel = str(path.relative_to(REPO_ROOT))
        tree = ast.parse(path.read_text())
        scopes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] or [tree]
        for scope in scopes:
            sites += _scope_sites(scope, models, rel)
    return sites


# (relpath-suffix, table, kind) — the complete list of RPC write sites on
# v14-committed tables as of EDGE-REG-CONSENSUS-1 (2026-10-21 audit). Every
# entry is a known residual hazard tracked for its own remediation row;
# any site not listed here fails the test.
#
#   gpu_resources register/allocate writers — REMOVED: gpu_registration
#     session.add + attr-mutation and gpu_allocation session.add moved to
#     the out-of-band writer route by 8bd0fa619 and 6e0f3c341 (FORK-OOB-1,
#     #382); only the edge_node_registration writer remains (de-committed
#     at v15 but still a hazard for every v14 block until activation)
#   escrow_routes account stub — REMOVED: the :1433 zero-balance account
#     write on POST /escrow/create is gone (8bd0fa619); the remaining
#     session.add calls touch escrow rows, not the account table
#   sync.py import path — full-chain import replaces account/chain_parameter*
#     (deletes + the insert loop; maintenance path, admin-only; documented
#     in the v3 design doc)
#   staking.py stake writers — the queue-time ``/v1/staking/*`` handlers the
#     v18 spec names as ``stake``'s only writers. ``stake`` leaves the
#     committed set at v18 (COMMITTED_TABLES_V18), re-scoping these rows to
#     service state — the same re-scope shape v15 proved for
#     edge_node_registration.
_ALLOWED: set[tuple[str, str, str]] = {
    ("rpc/gpu_resources.py", "edge_node_registration", "session.add"),
    ("rpc/gpu_resources.py", "edge_node_registration", "attr-mutation"),
    ("rpc/sync.py", "account", "sql.delete"),
    ("rpc/sync.py", "account", "session.add"),
    ("rpc/sync.py", "chain_parameter", "sql.delete"),
    ("rpc/sync.py", "chain_parameter_history", "sql.delete"),
    ("rpc/staking.py", "stake", "session.add"),
}


def test_no_new_rpc_writes_to_committed_tables() -> None:
    sites = _scan_rpc()
    unexpected = [s for s in sites if not any(s[0].endswith(f) and s[2] == t and s[3].startswith(k) for f, t, k in _ALLOWED)]
    assert unexpected == [], "new non-apply write sites against v14-committed tables (edge-reg-consensus-1):\n" + "\n".join(
        f"  {r}:{line} {t} via {k}" for r, line, t, k in unexpected
    )


def test_allowlist_is_not_stale() -> None:
    sites = {(s[0], s[2], s[3]) for s in _scan_rpc()}
    stale = [a for a in _ALLOWED if not any(r.endswith(a[0]) and t == a[1] and k.startswith(a[2]) for r, t, k in sites)]
    assert stale == [], f"allow-list entries no longer matching the tree: {stale}"
