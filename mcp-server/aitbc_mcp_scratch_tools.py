"""Scratch-file MCP tools confined to ``/var/tmp`` on the target node (#2441).

Scenario replay needs fixture files (quote/proof/media payloads) staged on a
node and cleaned up afterwards. Every path is normalized and must stay
beneath :data:`aitbc_mcp_server.SCRATCH_ROOT`; writes go through base64 so
content never touches a shell-quoted argv, and reads are size-capped.
"""

from __future__ import annotations

import base64
import posixpath
import shlex
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field

from aitbc_mcp_server import (
    SCRATCH_ROOT,
    NodeRole,
    _host_for_role,
    _json,
    _run_remote,
    mcp,
)

# Content caps: fixture payloads are small; the caps keep a runaway value from
# producing a giant argv/env or an unbounded stdout capture.
SCRATCH_WRITE_MAX_BYTES = 1024 * 1024
SCRATCH_READ_MAX_BYTES = 256 * 1024


def _scratch_path(path: str) -> str | None:
    """Normalize ``path`` and return it when it stays beneath ``SCRATCH_ROOT``."""
    if not isinstance(path, str) or not path.strip():
        return None
    norm = posixpath.normpath(path.strip())
    if norm != SCRATCH_ROOT and not norm.startswith(SCRATCH_ROOT + "/"):
        return None
    return norm


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True, open_world_hint=False))
def aitbc_scratch_file(
    action: Annotated[
        Literal["write", "read", "delete", "list"],
        Field(description="File operation to perform under the scratch root."),
    ],
    path: Annotated[
        str,
        Field(
            description=(
                f"Absolute path for the operation; must be {SCRATCH_ROOT}/<name> or beneath it "
                "(e.g. /var/tmp/<session>/quote.json). For 'list', the directory to list."
            )
        ),
    ],
    content: Annotated[
        str | None,
        Field(description="Text content for action='write' (UTF-8). Required for write, ignored otherwise."),
    ] = None,
    role: Annotated[
        NodeRole | None,
        Field(description="Node role where the file operation runs."),
    ] = None,
    host: Annotated[
        str | None,
        Field(description="Override the host for this call."),
    ] = None,
    timeout: Annotated[
        int,
        Field(description="Timeout in seconds.", ge=5, le=600),
    ] = 60,
) -> str:
    """Create, read, delete or list scratch files under ``/var/tmp`` on a node.

    Scratch space is where scenario legs stage fixture files (quotes, proofs,
    media) that ``run_aitbc_cli`` then references via ``--*-file`` options or
    ``cwd``/``env`` paths. Paths outside ``/var/tmp`` are refused, so the tool
    cannot touch ``/etc``, ``/var/lib/aitbc`` or user homes.

    Examples:
      - action="write", path="/var/tmp/s76/quote.json", content='{"price": "1.5"}'
      - action="read", path="/var/tmp/s76/quote.json"
      - action="delete", path="/var/tmp/s76/quote.json"
      - action="list", path="/var/tmp/s76"
    """
    target = _host_for_role(role, host)
    norm = _scratch_path(path)
    if norm is None:
        return _json(
            {
                "error": f"path must be {SCRATCH_ROOT}/<name> or beneath it",
                "path": path,
            }
        )
    qpath = shlex.quote(norm)

    if action == "write":
        if content is None:
            return _json({"error": "content is required for action='write'"})
        data = content.encode("utf-8")
        if len(data) > SCRATCH_WRITE_MAX_BYTES:
            return _json({"error": f"content exceeds {SCRATCH_WRITE_MAX_BYTES} bytes"})
        b64 = base64.b64encode(data).decode("ascii")
        qdir = shlex.quote(posixpath.dirname(norm))
        command = f"mkdir -p {qdir} && printf %s {shlex.quote(b64)} | base64 -d > {qpath} && wc -c < {qpath}"
    elif action == "read":
        # First stdout line is the byte size; the rest is content capped at
        # SCRATCH_READ_MAX_BYTES, so truncation is exact rather than guessed.
        command = f"stat -c %s -- {qpath} && head -c {SCRATCH_READ_MAX_BYTES} -- {qpath}"
    elif action == "delete":
        command = f"rm -f -- {qpath}"
    else:  # list
        command = f"ls -1A -- {qpath}"

    result = _run_remote(target, command, timeout)
    if action == "read" and result.get("returncode") == 0:
        size_line, _, content = result.get("stdout", "").partition("\n")
        try:
            size_bytes = int(size_line.strip())
        except ValueError:
            size_bytes = -1
        result["size_bytes"] = size_bytes
        result["stdout"] = content
        if size_bytes > SCRATCH_READ_MAX_BYTES:
            result["truncated"] = True
    result["path"] = norm
    result["action"] = action
    return _json(result)
