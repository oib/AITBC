#!/usr/bin/env python3
"""Ratchet: no fake-async route handlers.

An ``async def`` whose body contains no ``await``/``async for``/``async with``
runs its work directly on the event loop — the stall pattern fixed fleet-wide
under #723/#724/#726-#736. This check flags such functions in HTTP-facing
files (``*/routers/*.py``, ``*/routes/*.py``, ``*/rpc/*.py``) under apps/*/src
so new ones do not creep back in.

Legitimate pure-async handlers (e.g. a def whose decorators await it via a
framework hook that needs a coroutine, or one that schedules tasks without
awaiting) can opt out with ``# noqa: fake-async`` on the def line.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROUTE_DIRS = ("/routers/", "/routes/", "/rpc/")

# Calls that mark a body as legitimately async even without an await
# (task scheduling must run on the loop, not a worker thread).
LOOP_CALLS = ("create_task", "ensure_future", "get_event_loop", "get_running_loop", "asyncio")


def _route_file(path: str) -> bool:
    p = "/" + path.replace("\\", "/")
    return "/apps/" in p and "/src/" in p and any(d in p for d in ROUTE_DIRS)


def _is_async(node: ast.AST) -> bool:
    return isinstance(node, (ast.Await, ast.AsyncFor, ast.AsyncWith))


def violations(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return []
    lines = path.read_text().splitlines()
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if any(_is_async(x) for x in ast.walk(node)):
            continue
        if any(isinstance(x, ast.Call) and any(m in ast.dump(x.func) for m in LOOP_CALLS) for x in ast.walk(node)):
            continue
        defline = lines[node.lineno - 1] if node.lineno - 1 < len(lines) else ""
        if "# noqa: fake-async" in defline:
            continue
        found.append((node.lineno, node.name))
    return found


def main(argv: list[str]) -> int:
    bad = []
    for arg in argv:
        p = Path(arg)
        if not _route_file(str(p)) or not p.exists():
            continue
        for lineno, name in violations(p):
            bad.append(f"{p}:{lineno}: fake-async handler '{name}' — async def with no await (#723 pattern)")
    if bad:
        print("\n".join(bad))
        print(
            "\nConvert to `def` (FastAPI runs sync handlers on the threadpool) "
            "or add `# noqa: fake-async` on the def line with a comment why."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
