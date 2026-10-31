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


def _scan_scope() -> list[Path]:
    out: list[Path] = []
    for d in SCOPE_DIRS:
        root = REPO_ROOT / d
        if root.is_dir():
            out.extend(p for p in root.rglob("*.py") if "tests" not in p.parts and "__pycache__" not in p.parts)
    return out


def findings(path: Path) -> list[int]:
    """Line numbers of unawaited dangerous-verb calls inside async defs."""
    try:
        text = path.read_text()
        tree = ast.parse(text)
    except (SyntaxError, UnicodeDecodeError):
        return []
    lines = text.splitlines()
    found: list[int] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Expr) or not isinstance(sub.value, ast.Call):
                continue
            call = sub.value
            if not isinstance(call.func, ast.Attribute) or call.func.attr not in DANGEROUS_VERBS:
                continue
            line = lines[call.lineno - 1] if call.lineno - 1 <= len(lines) else ""
            if "# noqa: unawaited-async" in line:
                continue
            found.append(call.lineno)
    return found


def _load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {ln.strip() for ln in BASELINE.read_text().splitlines() if ln.strip() and not ln.startswith("#")}


def main(argv: list[str]) -> int:
    if "--update" in argv:
        out = []
        for p in _scan_scope():
            for ln in findings(p):
                out.append(f"{p.relative_to(REPO_ROOT)}:{ln}")
        BASELINE.write_text(
            "# unawaited-async findings baseline — regenerate: check-unawaited-async.py --update\n"
            + "\n".join(sorted(out))
            + "\n"
        )
        print(f"baseline updated: {len(out)} findings across scope")
        return 0

    paths = _scan_scope() if "--all" in argv or not argv else [Path(a) for a in argv if a.endswith(".py")]
    baseline = _load_baseline()
    bad = []
    for p in paths:
        if not p.exists():
            continue
        rel = str(p.resolve().relative_to(REPO_ROOT)) if p.is_absolute() else str(p)
        for ln in findings(p):
            if f"{rel}:{ln}" not in baseline:
                bad.append(f"{rel}:{ln}: unawaited coroutine-shaped call (#738/#749 class)")

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
