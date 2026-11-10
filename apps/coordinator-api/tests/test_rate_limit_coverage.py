"""Pin #1601: every mutating coordinator-api route carries a rate limit.

Before this change 75 mutating endpoints across 15 router files had no
throttle, and 7 of the 8 ``rate_limit_*`` settings were dead config. This
test walks the AST of ``src/coordinator_api`` and fails if any
``@router.post/put/delete/patch`` handler lacks an ``@rate_limit`` or
``@limiter.limit`` decorator, and asserts the settings-driven decorators
stayed wired to their routes.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "coordinator_api"

MUTATING_METHODS = {"post", "put", "delete", "patch"}
RATE_LIMIT_DECORATORS = {"rate_limit", "limit"}

# Settings that must stay wired into a route decorator (#1601 dead config).
SETTINGS_WIRING = {
    "contexts/infrastructure/routers/client.py": ["settings.rate_limit_jobs_submit"],
    "contexts/infrastructure/routers/miner.py": [
        "settings.rate_limit_miner_register",
        "settings.rate_limit_miner_heartbeat",
    ],
    "contexts/infrastructure/routers/admin.py": ["settings.rate_limit_admin_stats"],
    "contexts/infrastructure/routers/exchange.py": ["settings.rate_limit_exchange_payment"],
    "contexts/market/routers/market.py": [
        "settings.rate_limit_market_list",
        "settings.rate_limit_market_stats",
    ],
}


def _decorator_name(node: ast.expr) -> str | None:
    """Return the callable name of a decorator (``rate_limit``, ``limiter.limit`` -> ``limit``)."""
    func = node.func if isinstance(node, ast.Call) else node
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _unthrottled_mutating_handlers() -> list[str]:
    missing: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if _decorator_name(dec) in MUTATING_METHODS:
                    if not any(_decorator_name(d) in RATE_LIMIT_DECORATORS for d in node.decorator_list):
                        missing.append(f"{path.relative_to(SRC)}:{node.lineno}")
                    break
    return missing


def test_every_mutating_route_is_rate_limited() -> None:
    missing = _unthrottled_mutating_handlers()
    assert not missing, "Mutating coordinator-api routes without a rate limit:\n" + "\n".join(missing)


def test_rate_limit_settings_stay_wired() -> None:
    """The rate_limit_* settings must be referenced by the matching router."""
    for rel, needles in SETTINGS_WIRING.items():
        text = (SRC / rel).read_text()
        for needle in needles:
            assert needle in text, f"{rel} no longer wires {needle} — dead config regression (#1601)"


def test_rate_limited_handlers_can_identify_the_caller() -> None:
    """The shared decorator keys on the client IP, which needs a Request param.

    A mutating handler whose signature carries no starlette ``Request``
    parameter makes every caller share the ``"unknown"`` bucket — one client
    can then lock out everyone (#1601 follow-up: 26 endpoints had the body
    param named ``request`` or no request param at all).
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            has_rl = any(_decorator_name(d) == "rate_limit" for d in node.decorator_list)
            if not has_rl:
                continue
            has_mutating_route = any(_decorator_name(d) in MUTATING_METHODS for d in node.decorator_list)
            if not has_mutating_route:
                continue
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            has_request = any(
                arg.annotation is not None and ast.unparse(arg.annotation).split(".")[-1] == "Request" for arg in args
            )
            if not has_request:
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno} {node.name}")
    assert not offenders, "Rate-limited mutating handlers without a Request parameter:\n" + "\n".join(offenders)


def test_newly_limited_route_returns_429(client) -> None:
    """Functional pin: a previously unthrottled mutating route now 429s.

    ``POST /v1/agent-creativity/capabilities`` was one of the 75 endpoints
    with no throttle (#1601); it is limited to 20/minute. The handler may
    fail internally — the decorator runs first, so every attempt counts.
    """
    from aitbc.auth import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token('rl-pin', 'admin')}"}
    body = {
        "agent_id": "agent-rl",
        "creative_domain": "design",
        "capability_type": "generative",
        "generation_models": ["m1"],
    }
    codes = [client.post("/v1/agent-creativity/capabilities", json=body, headers=headers).status_code for _ in range(25)]
    assert 429 in codes, f"expected a 429 within 25 calls, got {codes}"
    assert codes[-1] == 429
