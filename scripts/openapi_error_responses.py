#!/usr/bin/env python3
"""Document the error responses the handlers actually return.

V23-80. Across the five published specs there were **703 operations and not one documented
response other than 2xx and 422** -- no 404, no 403, no 401, no 409, no 5xx. FastAPI infers a
response schema from a handler's return annotation and adds 422 where a request model can
fail validation. It cannot see a `raise HTTPException(404, ...)` or a
`return JSONResponse(status_code=404, ...)` in the body, because neither shows up in a
signature. So every "not found" in this repository was absent from its own contract.

V23-76 is what that costs. `GET /v1/marketplace/offers/{id}` answered 200 with a body of
`null` for a missing offer while its six siblings over the same resource answered 404, and
the published spec documented `200` and `422` for all eight -- so the documentation said they
agreed. It was wrong about six of them rather than right about any, and the one route that
really did disagree was indistinguishable from the rest.

Rather than hand-annotate `responses={...}` on 703 operations -- which would be stale by the
next release and could not be checked -- this reads the handler and reports what it finds:

* the status code from `HTTPException(...)`, `JSONResponse(...)`, `Response(...)` and
  `PlainTextResponse(...)`, whether written as an int or as `status.HTTP_404_NOT_FOUND`;
* the body shape, which is `{"detail": ...}` for `HTTPException` and the literal keys of
  `content={...}` for a `JSONResponse` -- the two disagree in this repository and pretending
  otherwise would document a body no client will receive;
* the message, when it is a literal, as the response description.

**Only literals are collected, and only from the handler's own source and its route
dependencies.** A code computed at runtime, or raised inside a service method the handler
calls, is not found. That makes the output a floor rather than a ceiling: everything
documented is genuinely reachable, and some reachable responses are still missing. A floor
that is derived and regenerable is worth more than a ceiling that is hand-written and rots --
`make openapi-check` fails the moment a handler and its spec disagree.

Nothing already present in the spec is overwritten. A route that declares its own
`responses={404: ...}` keeps exactly what it declared.
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

# The constructors whose status code lands in the response. `HTTPException` is raised;
# the rest are returned. Both reach the client the same way and neither is visible to
# FastAPI's schema inference.
_RESPONSE_CALLS = frozenset({"HTTPException", "JSONResponse", "Response", "PlainTextResponse"})

# `status.HTTP_404_NOT_FOUND` and `starlette.status.HTTP_404_NOT_FOUND` alike. 169 of the
# call sites in this repository spell the code this way rather than as an int, and an
# earlier version of this scan that matched only `ast.Constant` missed every one of them.
_STATUS_CONST = re.compile(r"^HTTP_(\d{3})_")

# The shape `HTTPException` produces. Everything else carries its own literal keys.
DETAIL_SHAPE = ("detail",)

ERROR_SCHEMA_NAME = "ErrorResponse"
ERROR_SCHEMA = {
    "title": ERROR_SCHEMA_NAME,
    "type": "object",
    "properties": {"detail": {"type": "string", "title": "Detail"}},
    "required": ["detail"],
    "description": "Raised as `HTTPException`; FastAPI serialises it under `detail`.",
}

# Enough messages to be useful in a client's error handling, not so many that the
# description becomes the handler's source code.
_MAX_MESSAGES = 4


@dataclass
class ErrorResponse:
    """One status code an operation can answer with, and how."""

    code: int
    shapes: set[tuple[str, ...]] = field(default_factory=set)
    messages: list[str] = field(default_factory=list)

    def description(self) -> str:
        """Prefer the handler's own words; fall back to the status code's meaning."""
        if not self.messages:
            return _reason(self.code)
        shown = self.messages[:_MAX_MESSAGES]
        text = " / ".join(shown)
        if len(self.messages) > _MAX_MESSAGES:
            text += " / …"
        return text

    def schema(self) -> dict[str, Any] | None:
        """The response body, or None when the handler sends no JSON object."""
        schemas = [_shape_schema(shape) for shape in sorted(self.shapes)]
        schemas = [s for s in schemas if s is not None]
        if not schemas:
            return None
        if len(schemas) == 1:
            return schemas[0]
        # One handler answering the same code in two shapes is a defect, not something to
        # smooth over. `anyOf` says so in the document instead of picking a winner.
        return {"anyOf": schemas}


def _reason(code: int) -> str:
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return f"Error {code}"


def _shape_schema(shape: tuple[str, ...]) -> dict[str, Any] | None:
    if shape == DETAIL_SHAPE:
        return {"$ref": f"#/components/schemas/{ERROR_SCHEMA_NAME}"}
    if not shape:
        # `Response(status_code=503)` with no content, or a `content=` this scan could not
        # read. Documenting the code without inventing a body for it.
        return None
    return {
        "type": "object",
        "properties": {key: {"title": key.replace("_", " ").title()} for key in shape},
    }


def _status_code(node: ast.expr) -> int | None:
    """An `int` literal or a `status.HTTP_NNN_*` attribute; anything else is unknown."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Attribute) and (m := _STATUS_CONST.match(node.attr)):
        return int(m.group(1))
    if isinstance(node, ast.Name) and (m := _STATUS_CONST.match(node.id)):
        return int(m.group(1))
    return None


def _message(node: ast.expr) -> str | None:
    """A literal message, with f-string placeholders kept as `{name}`.

    `f"Edge node {node_id} not found"` is more informative to a client than "Not Found",
    and the placeholder is the part that tells them what the message is about.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip() or None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("{" + ast.unparse(value.value) + "}")
        rendered = "".join(parts).strip()
        return rendered or None
    return None


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return getattr(node.func, "id", "")


def _source_tree(fn: Any) -> ast.AST | None:
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return None
    try:
        return ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return None


def _scan(fn: Any, found: dict[int, ErrorResponse]) -> None:
    """Add every literal >=400 response constructed in `fn`'s own source to `found`."""
    tree = _source_tree(fn)
    if tree is None:
        return

    # Source order, not `ast.walk` order. `walk` is breadth-first, so the last branch of a
    # handler would be described first -- stable, but arbitrary, and the truncated message
    # list would keep whichever four the tree shape happened to surface.
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) in _RESPONSE_CALLS]
    calls.sort(key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))

    for node in calls:
        name = _call_name(node)
        code: int | None = None
        shape: tuple[str, ...] = ()
        message: str | None = None

        # `HTTPException(404, "...")` and `JSONResponse({...}, 404)` both pass positionally
        # in this repository, and the position means something different in each.
        if node.args:
            if name == "HTTPException":
                code = _status_code(node.args[0])
                if len(node.args) > 1:
                    message = _message(node.args[1])
            elif len(node.args) > 1:
                code = _status_code(node.args[1])

        for keyword in node.keywords:
            if keyword.arg in {"status_code", "status"}:
                code = _status_code(keyword.value) or code
            elif keyword.arg == "detail":
                message = _message(keyword.value)
            elif keyword.arg == "content" and isinstance(keyword.value, ast.Dict):
                keys = keyword.value.keys
                # `{**base, "error": ...}` -- a `**` spread parses as a None key. The keys
                # that survive are a subset, and a subset published as the body is a
                # schema the client can fail to match. Document the code, not a half body.
                if all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in keys):
                    shape = tuple(sorted(key.value for key in keys))  # type: ignore[union-attr]
                for key, value in zip(keyword.value.keys, keyword.value.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value in {"error", "detail", "message"}:
                        message = _message(value) or message

        if code is None or code < 400:
            continue

        if name == "HTTPException":
            shape = DETAIL_SHAPE

        entry = found.setdefault(code, ErrorResponse(code=code))
        entry.shapes.add(shape)
        if message and message not in entry.messages:
            entry.messages.append(message)


def collect(endpoint: Any, dependencies: tuple[Any, ...] = ()) -> dict[int, ErrorResponse]:
    """Every error response reachable from a route's own handler and its dependencies.

    Dependencies matter for exactly one thing here and it is the important one: the
    security dependencies raise the 401 that a client is most likely to have to handle,
    and no handler body mentions it.
    """
    found: dict[int, ErrorResponse] = {}
    _scan(endpoint, found)
    for dependency in dependencies:
        _scan(dependency, found)
    return found


def _dependency_callables(route: Any) -> tuple[Any, ...]:
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return ()
    return tuple(d.call for d in dependant.dependencies if d.call is not None)


def enrich(spec: dict[str, Any], app: Any) -> dict[str, Any]:
    """Add each operation's derived error responses to an already-generated spec.

    Written as a pass over the finished document rather than as a FastAPI override so that
    it stays a property of what gets published, and so a service's own `/openapi.json` is
    not made to depend on an AST scan at request time.
    """
    from fastapi.routing import APIRoute

    # `openapi_prefix`/`root_path` aside, `route.path` is the key used in `paths`.
    by_path: dict[tuple[str, str], Any] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods:
            by_path[(route.path, method.lower())] = route

    used_detail_schema = False
    for path, item in spec.get("paths", {}).items():
        for method, operation in item.items():
            route = by_path.get((path, method.lower()))
            if route is None or not isinstance(operation, dict):
                continue
            responses = operation.setdefault("responses", {})
            for code, error in sorted(collect(route.endpoint, _dependency_callables(route)).items()):
                key = str(code)
                # An explicit `responses={...}` on the route is the author saying what this
                # operation returns. It wins.
                if key in responses:
                    continue
                response: dict[str, Any] = {"description": error.description()}
                schema = error.schema()
                if schema is not None:
                    response["content"] = {"application/json": {"schema": schema}}
                    used_detail_schema |= DETAIL_SHAPE in error.shapes
                responses[key] = response

    if used_detail_schema:
        schemas = spec.setdefault("components", {}).setdefault("schemas", {})
        schemas.setdefault(ERROR_SCHEMA_NAME, ERROR_SCHEMA)

    return spec
