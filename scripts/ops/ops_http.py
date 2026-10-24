"""Shared HTTP transport for the scripts/ops audit tools.

Extracted from post-cut-verify.py (UNPAUSE-PRECHECK-SSH-1, #398) so
unpause-precheck.py routes per-host RPC reads through ``ssh <alias> curl``
when the manifest marks a host ``rpc_via_ssh`` — the same escape that
fixed the dead tunnel URLs there. Consumers load this file by location
(the scripts run as ``python3 scripts/ops/<tool>.py`` and tests load them
via ``spec_from_file_location``, so no package import is possible) and
re-bind the names they use.

Every function takes a duck-typed ``ctx``: it needs ``.manifest`` (dict)
and the ``.http_get`` / ``.http_post`` / ``.host_sh`` callables each
consumer's Ctx already injects for tests.
"""

import json
import shlex
import time


def sh(ctx, hspec: dict, cmd: str):
    return ctx.host_sh(hspec.get("ssh"), cmd)


def _ssh_curl(ctx, alias: str, argv_tail: list[str]) -> tuple[int, dict]:
    """One HTTP request through ``ssh <alias> curl`` — for listeners bound
    to the remote loopback that no local tunnel reaches (manifest
    ``rpc_via_ssh``/``prom_via_ssh``). The remote curl prints the body,
    then ``\\n%{http_code}``; the last stdout line is the status and
    everything above it the body. ``(-1, …)`` marks a transport failure —
    the ssh leg died or curl never printed a status — so ``_retry`` treats
    it exactly like an unanswered socket."""
    cmd = "curl -s -m 10 -w '\\n%{http_code}' " + " ".join(argv_tail)
    out = ctx.host_sh(alias, cmd)
    if not out:
        return -1, {"error": f"ssh {alias} curl: no output"}
    lines = out.splitlines()
    try:
        code = int(lines[-1].strip())
    except (IndexError, ValueError):
        return -1, {"error": f"ssh {alias} curl: bad status line {out[-80:]!r}"}
    try:
        return code, json.loads("\n".join(lines[:-1]))
    except Exception:
        return code, {}


def _get_via_ssh(ctx, hspec: dict, url: str) -> tuple[int, dict]:
    alias = hspec.get("ssh")
    if not alias:
        return -1, {"error": "rpc_via_ssh set but host has no ssh alias"}
    return _retry(ctx, lambda: _ssh_curl(ctx, alias, [shlex.quote(url)]))


def hget(ctx, hspec: dict, path: str) -> tuple[int, dict]:
    url = hspec["rpc"].rstrip("/") + path
    if hspec.get("rpc_via_ssh"):
        return _get_via_ssh(ctx, hspec, url)
    return _get(ctx, url)


def hpost(ctx, hspec: dict, path: str, body: dict) -> tuple[int, dict]:
    url = hspec["rpc"].rstrip("/") + path
    if not hspec.get("rpc_via_ssh"):
        return ctx.http_post(url, body)
    return _retry(
        ctx,
        lambda: _ssh_curl(
            ctx,
            hspec["ssh"],
            [
                "-X",
                "POST",
                "-H",
                shlex.quote("Content-Type: application/json"),
                "--data",
                shlex.quote(json.dumps(body)),
                shlex.quote(url),
            ],
        ),
    )


def _get(ctx, url: str) -> tuple[int, dict]:
    return _retry(ctx, lambda: ctx.http_get(url))


def _retry(ctx, fetch) -> tuple[int, dict]:
    """Bounded retry on transport failures only.

    ``code == -1`` means the request never got an HTTP answer — timeout,
    refused, or a dropped leg (the ssh-curl legs stall under load the same
    way a dead tunnel does); a short backoff absorbs that without masking
    definitive answers: real status codes, even 5xx, return on the first
    attempt. Tunables: expected.http_attempts (default 3),
    expected.http_retry_backoff_s (default 0.4, doubled per retry).
    """
    exp = ctx.manifest.get("expected") or {}
    attempts = max(1, int(exp.get("http_attempts", 3)))
    backoff = float(exp.get("http_retry_backoff_s", 0.4))
    code, body = fetch()
    for i in range(attempts - 1):
        if code != -1:
            break
        time.sleep(backoff * (2**i))
        code, body = fetch()
    return code, body
