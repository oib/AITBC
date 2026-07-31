"""Security hardening tests for HTTPException 5xx detail strings."""

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
                failures.append(
                    f"{py_file}:{raise_node.lineno}: hardened 5xx raise lacks preceding logging.exception call"
                )
    assert not failures, "\n".join(failures)
