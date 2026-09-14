"""Security hardening tests for 5xx response bodies.

A 5xx body is written for an untrusted caller. The exception that caused it is
not: it carries DSNs, RPC URLs, addresses and internal paths, and these services
are reachable from the internet through the hub containers' nginx. So the rule
is that the caught exception goes to the log and never to the response.
"""

import ast
from pathlib import Path

import pytest

APPS_DIR = Path(__file__).parents[2] / "apps"


def _is_5xx_status(value: ast.expr) -> bool:
    """Return True if the AST expression denotes a 5xx HTTP status code."""
    if isinstance(value, ast.Constant) and isinstance(value.value, int):
        return 500 <= value.value < 600
    if isinstance(value, ast.Attribute):
        return value.attr.startswith("HTTP_5")
    if isinstance(value, ast.Name):
        return value.id.startswith("HTTP_5")
    return False


def _detail_value(value: ast.expr) -> str | None:
    """Return the string detail for an AST expression, or None if not a plain string."""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _collect_http_exception_raises(tree: ast.AST) -> list[ast.Raise]:
    """Find all raise HTTPException(...) nodes in an AST."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        and node.exc is not None
        and isinstance(node.exc, ast.Call)
        and (
            (isinstance(node.exc.func, ast.Name) and node.exc.func.id == "HTTPException")
            or (isinstance(node.exc.func, ast.Attribute) and node.exc.func.attr == "HTTPException")
        )
    ]


def _service_py_files(service_name: str) -> list[Path]:
    return list((APPS_DIR / service_name).rglob("*.py"))


def _services_with_5xx() -> list[str]:
    """Discover services that contain at least one 5xx HTTPException site."""
    services: set[str] = set()
    for service_dir in sorted(APPS_DIR.iterdir()):
        if not service_dir.is_dir():
            continue
        for py_file in service_dir.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except Exception:  # pragma: no cover
                continue
            for raise_node in _collect_http_exception_raises(tree):
                status = next(
                    (kw.value for kw in raise_node.exc.keywords if kw.arg == "status_code"),
                    None,
                )
                if status is not None and _is_5xx_status(status):
                    services.add(service_dir.name)
                    break
    return sorted(services)


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _nearest_except_handler(raise_node: ast.Raise, parents: dict[ast.AST, ast.AST]) -> ast.ExceptHandler | None:
    current: ast.AST | None = raise_node
    while current is not None:
        if isinstance(current, ast.ExceptHandler):
            return current
        current = parents.get(current)
    return None


def _has_prior_exception_log_in_handler(handler: ast.ExceptHandler, raise_node: ast.Raise) -> bool:
    """Return True if the handler contains a logging.exception('Unhandled exception') call before the raise."""
    for node in ast.walk(handler):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "exception"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "Unhandled exception"
            and (node.lineno is not None and raise_node.lineno is not None and node.lineno < raise_node.lineno)
        ):
            return True
    return False


@pytest.mark.parametrize("service_name", _services_with_5xx())
def test_no_5xx_raw_exception_detail(service_name: str) -> None:
    """No 5xx HTTPException uses detail=str(...) or a formatted string with the exception."""
    failures: list[str] = []
    for py_file in _service_py_files(service_name):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:  # pragma: no cover
            continue
        for raise_node in _collect_http_exception_raises(tree):
            status = next(
                (kw.value for kw in raise_node.exc.keywords if kw.arg == "status_code"),
                None,
            )
            if status is None or not _is_5xx_status(status):
                continue
            detail = next(
                (kw.value for kw in raise_node.exc.keywords if kw.arg == "detail"),
                None,
            )
            if detail is None:
                continue
            # formatted string (f"...{str(e)}...") or direct str(...) call
            if isinstance(detail, ast.JoinedStr):
                failures.append(f"{py_file}:{raise_node.lineno}: f-string detail for 5xx HTTPException")
            elif isinstance(detail, ast.Call) and isinstance(detail.func, ast.Name) and detail.func.id == "str":
                failures.append(f"{py_file}:{raise_node.lineno}: detail=str(...) for 5xx HTTPException")
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("service_name", _services_with_5xx())
def test_5xx_error_paths_log_and_return_generic_detail(service_name: str) -> None:
    """Every hardened 5xx HTTPException is preceded by a logging.exception call and uses a generic detail."""
    failures: list[str] = []
    for py_file in _service_py_files(service_name):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:  # pragma: no cover
            continue
        parents = _parent_map(tree)
        for raise_node in _collect_http_exception_raises(tree):
            status = next(
                (kw.value for kw in raise_node.exc.keywords if kw.arg == "status_code"),
                None,
            )
            if status is None or not _is_5xx_status(status):
                continue
            detail = next(
                (kw.value for kw in raise_node.exc.keywords if kw.arg == "detail"),
                None,
            )
            if detail is None:
                continue
            detail_text = _detail_value(detail)
            if detail_text != "Internal server error":
                # Not a hardened raw-exception site; do not require logging for it
                continue
            # If the raise is inside an except block, it must log the original exception.
            handler = _nearest_except_handler(raise_node, parents)
            if handler is None:
                continue
            if not _has_prior_exception_log_in_handler(handler, raise_node):
                failures.append(f"{py_file}:{raise_node.lineno}: hardened 5xx raise lacks preceding logging.exception call")
    assert not failures, "\n".join(failures)


RESPONSE_FACTORIES = frozenset(
    {"JSONResponse", "ORJSONResponse", "UJSONResponse", "PlainTextResponse", "HTMLResponse", "Response"}
)


def _is_response_construct(node: ast.expr) -> bool:
    """True for a Starlette/FastAPI response object built in a `return`, not raised."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in RESPONSE_FACTORIES
    if isinstance(func, ast.Attribute):
        return func.attr in RESPONSE_FACTORIES
    return False


def _is_http_exception_construct(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    return (isinstance(node.func, ast.Name) and node.func.id == "HTTPException") or (
        isinstance(node.func, ast.Attribute) and node.func.attr == "HTTPException"
    )


def _five_xx_constructs(tree: ast.AST) -> list[ast.Call]:
    """Every call building a 5xx response, whether it is raised or returned."""
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (_is_http_exception_construct(node) or _is_response_construct(node)):
            continue
        status = next((kw.value for kw in node.keywords if kw.arg == "status_code"), None)
        if status is not None and _is_5xx_status(status):
            found.append(node)
    return found


def _enclosing_exception_names(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> set[str]:
    """The names bound by the `except ... as <name>` handlers this node sits inside."""
    names: set[str] = set()
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, ast.ExceptHandler) and current.name:
            names.add(current.name)
        current = parents.get(current)
    return names


def _services_with_5xx_response() -> list[str]:
    """Discover services that build a 5xx response by any of the two routes."""
    services: set[str] = set()
    for service_dir in sorted(APPS_DIR.iterdir()):
        if not service_dir.is_dir():
            continue
        for py_file in service_dir.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except Exception:  # pragma: no cover
                continue
            if _five_xx_constructs(tree):
                services.add(service_dir.name)
                break
    return sorted(services)


@pytest.mark.parametrize("service_name", _services_with_5xx_response())
def test_no_5xx_response_carries_the_caught_exception(service_name: str) -> None:
    """No 5xx body references the exception its handler caught.

    Wider than test_no_5xx_raw_exception_detail in two directions, and narrower
    in one that matters. Wider: it sees `return JSONResponse(...)` as well as
    `raise HTTPException(...)` -- 30 sites across six services returned the
    exception that way, invisible to a check that only walks `raise` -- and it
    matches any reference to the bound name, not just the two spellings
    `str(e)` and f-string, so `e.args`, `repr(exc)` and `{"error": e}` are
    findings too.

    Narrower: it fires only when the interpolated name is bound by an enclosing
    `except ... as`, so an f-string naming the service being proxied is not a
    finding. That distinction is the whole reason this is a separate rule --
    without it the api-gateway circuit-breaker messages, which interpolate a
    route name the caller supplied in the first place, would have to be
    allowlisted by hand.
    """
    failures: list[str] = []
    for py_file in _service_py_files(service_name):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover
            continue
        parents = _parent_map(tree)
        for call in _five_xx_constructs(tree):
            bound = _enclosing_exception_names(call, parents)
            if not bound:
                continue
            leaked = sorted({n.id for n in ast.walk(call) if isinstance(n, ast.Name) and n.id in bound})
            if leaked:
                failures.append(f"{py_file}:{call.lineno}: 5xx body references the caught exception ({', '.join(leaked)})")
    assert not failures, "\n".join(failures)
