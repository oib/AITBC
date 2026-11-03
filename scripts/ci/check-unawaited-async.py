#!/usr/bin/env python3
"""Ratchet: no unawaited coroutine calls.

A bare-statement call to an async method inside an ``async def`` discards the
coroutine — the write/close/publish never runs. This is the class behind
#738 (``sqlite_conn.close()`` never executed) and #749 (``redis.set(...)``
unawaited on ``redis.asyncio`` — nonces never persisted). Neither ruff nor
mypy flags a discarded coroutine call, so this AST check is the gate.

What it flags: inside an ``async def``, an ``Expr`` statement whose value is
a ``Call`` on an attribute whose name is a dangerous async verb (redis /
aiosqlite / AsyncSession / httpx / ws / queue shapes). It cannot type-check,
so verified-sync receivers with the same method name (``session.commit()`` on
a sync Session, ``conn.execute()`` on sqlite3) are absorbed by the baseline
file — only *new* findings fail.

Usage:

    scripts/ci/check-unawaited-async.py file1.py [file2.py ...]   # changed-file mode (pre-commit)
    scripts/ci/check-unawaited-async.py --all                     # whole-scope scan (manual CI)
    scripts/ci/check-unawaited-async.py --update                  # regenerate baseline

Opt out for a deliberately fire-and-forget or sync receiver:
``# noqa: unawaited-async`` on the call line.

Test paths are outside the ratchet's scope in every mode — changed-file
arguments and the whole-scope scan apply the same filter, so ``--update``
never writes baseline lines under ``tests/``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "scripts" / "ci" / "unawaited-async-baseline.txt"

# Scan scope for --all (mirrors the mypy/ruff coverage footprint).
SCOPE_DIRS = ("apps", "cli", "packages/py", "mcp-server", "aitbc")

# Attribute names that are coroutine methods on the async clients this repo
# uses (redis.asyncio, aiosqlite, sqlalchemy AsyncSession/AsyncConnection,
# httpx.AsyncClient, websockets, asyncio.Queue/streams, broadcaster, motor).
# Names that are *almost always* async on a likely receiver come first;
# generic names overlap with sync objects and are why the baseline exists.
DANGEROUS_VERBS = frozenset(
    {
        # near-unambiguous async method names
        "aclose",
        "asend",
        "athrow",
        "publish",
        "subscribe",
        "unsubscribe",
        "psubscribe",
        "punsubscribe",
        "xadd",
        "xread",
        "xack",
        "blpop",
        "brpop",
        "setex",
        "setnx",
        "getset",
        "pexpire",
        "psetex",
        "mset",
        "mget",
        "hset",
        "hdel",
        "sadd",
        "srem",
        "rpush",
        "lpush",
        "zadd",
        "scalars",
        # generic verbs — coroutine on async receivers, sync elsewhere
        "set",
        "get",
        "delete",
        "expire",
        "commit",
        "rollback",
        "close",
        "save",
        "flush",
        "refresh",
        "execute",
        "exec",
        "send",
        "broadcast",
        "connect",
        "disconnect",
        "put",
        "incr",
        "decr",
        "exists",
        "keys",
        "scan",
        "eval",
        "lpop",
        "rpop",
        "ttl",
        "rename",
        "persist",
        "acquire",
        "release",
        "wait_closed",
        "drain",
        "run",
        "start",
        "stop",
        "insert",
        "update_one",
        "delete_one",
        "insert_one",
        "find_one",
        "drop",
    }
)


def _in_scope(p: Path) -> bool:
    return "tests" not in p.parts and "__pycache__" not in p.parts


def _scan_scope() -> list[Path]:
    out: list[Path] = []
    for d in SCOPE_DIRS:
        root = REPO_ROOT / d
        if root.is_dir():
            out.extend(p for p in root.rglob("*.py") if _in_scope(p))
    return out


def findings(path: Path) -> list[tuple[int, str, str]]:
    """(line, enclosing async-def name, normalized call source) per flagged call.

    Call source comes from ``ast.get_source_segment`` collapsed to one line —
    keying on it instead of the line number means moving code keeps a
    baselined finding baselined and a new call landing on an old line number
    cannot slip through (#984).
    """
    try:
        text = path.read_text()
        tree = ast.parse(text)
    except (SyntaxError, UnicodeDecodeError):
        return []
    lines = text.splitlines()
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    found: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr not in DANGEROUS_VERBS:
            continue
        line = lines[call.lineno - 1] if call.lineno - 1 <= len(lines) else ""
        if "# noqa: unawaited-async" in line:
            continue
        # Innermost enclosing function — the finding only counts when that is
        # an async def (a bare call inside a sync def nested under one is a
        # sync-context call, not a discarded coroutine).
        func = parents.get(node)
        while func is not None and not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = parents.get(func)
        if not isinstance(func, ast.AsyncFunctionDef):
            continue
        call_src = ast.get_source_segment(text, call) or f"<unknown>.{call.func.attr}(...)"
        found.append((call.lineno, func.name, " ".join(call_src.split())))
    return found


def _key(rel: str, func: str, call: str) -> str:
    return f"{rel}\t{func}\t{call}"


def _load_baseline() -> dict[str, int]:
    """key -> tolerated occurrence count (``key<TAB>count`` per line)."""
    out: dict[str, int] = {}
    if not BASELINE.exists():
        return out
    for ln in BASELINE.read_text().splitlines():
        ln = ln.rstrip()
        if not ln or ln.startswith("#"):
            continue
        key, _, count = ln.rpartition("\t")
        if not key:
            key, count = ln, "1"
        out[key] = out.get(key, 0) + (int(count) if count.isdigit() else 1)
    return out


def _scan_counts() -> dict[str, int]:
    """key -> occurrence count across the whole scope."""
    counts: dict[str, int] = {}
    for p in _scan_scope():
        rel = str(p.relative_to(REPO_ROOT))
        for _ln, func, call in findings(p):
            key = _key(rel, func, call)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _update_baseline() -> int:
    new_counts = _scan_counts()
    old = _load_baseline()
    added = {k: n - old.get(k, 0) for k, n in new_counts.items() if n > old.get(k, 0)}
    removed = {k: n - new_counts.get(k, 0) for k, n in old.items() if n > new_counts.get(k, 0)}
    lines = ["# unawaited-async findings baseline — regenerate: check-unawaited-async.py --update"]
    lines += [f"{key}\t{n}" for key, n in sorted(new_counts.items())]
    BASELINE.write_text("\n".join(lines) + "\n")
    print(f"baseline updated: {sum(new_counts.values())} findings, {len(new_counts)} keys across scope")
    for key, n in sorted(added.items()):
        print(f"  +{n} {key.replace(chr(9), ' :: ')}")
    for key, n in sorted(removed.items()):
        print(f"  -{n} {key.replace(chr(9), ' :: ')}")
    return 0


def _check(paths: list[Path]) -> tuple[list[str], dict[str, int]]:
    baseline = _load_baseline()
    seen: dict[str, int] = {}
    bad = []
    for p in paths:
        if not p.exists():
            continue
        rel = str(p.resolve().relative_to(REPO_ROOT)) if p.is_absolute() else str(p)
        for ln, func, call in findings(p):
            key = _key(rel, func, call)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > baseline.get(key, 0):
                bad.append(f"{rel}:{ln}: unawaited coroutine-shaped call in `{func}`: {call} (#738/#749 class)")
    return bad, seen


def main(argv: list[str]) -> int:
    if "--update" in argv:
        return _update_baseline()

    paths = (
        _scan_scope() if "--all" in argv or not argv else [Path(a) for a in argv if a.endswith(".py") and _in_scope(Path(a))]
    )
    baseline = _load_baseline()
    bad, seen = _check(paths)

    if "--all" in argv or not argv:
        stale = sorted(k for k, n in baseline.items() if seen.get(k, 0) < n)
        for k in stale:
            print(f"stale baseline entry: {k.replace(chr(9), ' :: ')} — matches nothing; regenerate with --update")
    if bad:
        print("\n".join(sorted(bad)))
        print(
            "\nA bare call to an async-shaped method inside `async def` discards the coroutine — "
            "the write/close never runs. Add `await`; if the receiver is deliberately sync or "
            "fire-and-forget, add `# noqa: unawaited-async` with a comment. To absorb verified "
            "false positives repo-wide: scripts/ci/check-unawaited-async.py --update"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
