"""Shared JSON body types for the HTTP client and its cache."""

from typing import Any

# The wire format is whatever the endpoint returns, and several of them return a JSON
# array: /rpc/transactions is the one that bit us. The client's methods used to be
# annotated `-> dict[str, Any]` and end in `cast(dict[str, Any], result)`, an unchecked
# assertion over `response.json()`. mypy believed it, so `isinstance(result, list)` read
# as unreachable at every call site, and a list flowing into `result.get(...)` was
# invisible to the type checker. Three call sites worked around that locally -- a
# `type: ignore[unreachable]`, an `: Any` annotation and a widened variable -- and a
# fourth avoided this client altogether.
JSONResponse = dict[str, Any] | list[Any]


def expect_object(result: JSONResponse, url: str) -> dict[str, Any]:
    """Narrow a decoded JSON body to an object, checking rather than asserting.

    This is what `cast(dict[str, Any], ...)` pretended to do. The overwhelming majority
    of endpoints return an object, so `get()`/`post()`/... keep their `dict[str, Any]`
    contract -- but they now *earn* it here. An endpoint that returns an array fails
    immediately, at the call, naming the URL; previously the array travelled on as a
    declared dict and surfaced as an `AttributeError: 'list' object has no attribute
    'get'` somewhere further down, or not at all.

    Callers of an array-returning endpoint should use `get_json()`, which returns the
    honest union and makes the type checker require a shape check.
    """
    if isinstance(result, dict):
        return result
    raise TypeError(
        f"{url} returned a JSON array, not an object. "
        f"Use get_json() and handle both shapes if this endpoint can return either."
    )
