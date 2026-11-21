"""Scratch-file MCP tools confined to ``/var/tmp`` on the target node (#2441).

Scenario replay needs fixture files (quote/proof/media payloads) staged on a
node and cleaned up afterwards. Every path is normalized and must stay
beneath :data:`aitbc_mcp_server.SCRATCH_ROOT`; writes go through base64 so
content never touches a shell-quoted argv, and reads are size-capped.

Commands are single ``python3 -c`` invocations (or plain ``rm``/``ls``) so
they work both through the remote login shell and the local ``execvp``
branch of ``_run_remote``, which cannot interpret ``&&``/pipes.
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

_PY_WRITE = (
    "import base64,sys,pathlib;"
    "p=pathlib.Path(sys.argv[1]);"
    "p.parent.mkdir(parents=True,exist_ok=True);"
    "d=base64.b64decode(sys.argv[2]);"
    "p.write_bytes(d);"
    "print(len(d))"
)
_PY_READ = (
    "import base64,sys,pathlib;"
    "d=pathlib.Path(sys.argv[1]).read_bytes();"
    "sys.stdout.write(str(len(d))+'\\n');"
    "sys.stdout.write(base64.b64encode(d[:" + str(SCRATCH_READ_MAX_BYTES) + "]).decode())"
)


def _scratch_path(path: str) -> str | None:
    """Normalize ``path`` and return it when it stays beneath ``SCRATCH_ROOT``."""
    if not isinstance(path, str) or not path.strip():
        return None
    norm = posixpath.normpath(path.strip())
    if norm != SCRATCH_ROOT and not norm.startswith(SCRATCH_ROOT + "/"):
        return None
    return norm


def _scratch_write_command(qpath: str, content: str | None, content_base64: str | None) -> tuple[str | None, str | None]:
    """Build the write command; returns ``(command, error)``."""
    if content is not None and content_base64 is not None:
        return None, "pass either content or content_base64, not both"
    if content_base64 is not None:
        try:
            data = base64.b64decode(content_base64, validate=True)
        except ValueError:
            return None, "content_base64 is not valid base64"
    elif content is not None:
        data = content.encode("utf-8")
    else:
        return None, "content or content_base64 is required for action='write'"
    if len(data) > SCRATCH_WRITE_MAX_BYTES:
        return None, f"content exceeds {SCRATCH_WRITE_MAX_BYTES} bytes"
    b64 = base64.b64encode(data).decode("ascii")
    return f"python3 -c {shlex.quote(_PY_WRITE)} {qpath} {shlex.quote(b64)}", None


def _scratch_read_result(result: dict) -> dict:
    """Decode the ``size\\n<base64>`` read payload into the result envelope."""
    if result.get("returncode") != 0:
        return result
    raw = result.get("stdout", "")
    size_line, _, content_b64 = raw.partition("\n")
    try:
        size_bytes = int(size_line.strip())
    except ValueError:
        size_bytes = -1
    result["size_bytes"] = size_bytes
    try:
        data = base64.b64decode(content_b64.strip(), validate=True)
        result["stdout"] = data.decode("utf-8")
        result["encoding"] = "utf-8"
    except (ValueError, UnicodeDecodeError):
        result["stdout"] = ""
        result["content_base64"] = content_b64.strip()
        result["encoding"] = "base64"
    if size_bytes > SCRATCH_READ_MAX_BYTES:
        result["truncated"] = True
    return result


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
        Field(description="Text content for action='write' (UTF-8). Required for write unless content_base64 is given."),
    ] = None,
    content_base64: Annotated[
        str | None,
        Field(description="Base64-encoded bytes for action='write' — use for binary fixtures instead of content."),
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

    command: str
    if action == "write":
        cmd, error = _scratch_write_command(qpath, content, content_base64)
        if error or cmd is None:
            return _json({"error": error or "failed to build write command"})
        command = cmd
    elif action == "read":
        command = f"python3 -c {shlex.quote(_PY_READ)} {qpath}"
    elif action == "delete":
        command = f"rm -f -- {qpath}"
    else:  # list
        command = f"ls -1A -- {qpath}"

    result = _run_remote(target, command, timeout)
    if action == "read":
        result = _scratch_read_result(result)
    result["path"] = norm
    result["action"] = action
    return _json(result)
