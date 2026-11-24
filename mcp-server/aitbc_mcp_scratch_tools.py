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
    _build_dry_run,
    _execution_context,
    _host_for_role,
    _json,
    _run_remote,
    mcp,
)

# Content caps: fixture payloads are small; the caps keep a runaway value from
# producing a giant argv/env or an unbounded stdout capture.
SCRATCH_WRITE_MAX_BYTES = 1024 * 1024
SCRATCH_READ_MAX_BYTES = 256 * 1024

# #2498: the lexical check in ``_scratch_path`` is not sufficient — a symlink
# inside /var/tmp pointing outside would let read/write/delete/list escape the
# root (the tool runs as root on the node). Every remote snippet therefore
# opens with a realpath guard: resolve the target, require it to stay beneath
# the resolved scratch root, and exit 3 otherwise. ``r`` is the resolved path
# the body then operates on, so in-root symlinks still work.
_PY_GUARD = (
    "import os,sys\n"
    f"root=os.path.realpath({SCRATCH_ROOT!r})\n"
    "r=os.path.realpath(sys.argv[1])\n"
    "if not (r==root or r.startswith(root+'/')):\n"
    "    sys.stderr.write('scratch path escapes '+root+': '+sys.argv[1]+' -> '+r+'\\n')\n"
    "    sys.exit(3)\n"
)

# #2505: the payload rides stdin, not argv — a single argv string is capped
# at MAX_ARG_STRLEN (~128 KiB), so base64 content above ~96 KiB raised
# OSError E2BIG. stdin has no such limit and never lands in ``ps``.
_PY_WRITE = (
    _PY_GUARD
    + "import base64,pathlib\n"
    + "p=pathlib.Path(r)\n"
    + "p.parent.mkdir(parents=True,exist_ok=True)\n"
    + "d=base64.b64decode(sys.stdin.buffer.read())\n"
    + "p.write_bytes(d)\n"
    + "print(len(d))\n"
)
_PY_READ = (
    _PY_GUARD
    + "import base64,pathlib\n"
    + "d=pathlib.Path(r).read_bytes()\n"
    + "sys.stdout.write(str(len(d))+'\\n')\n"
    + "sys.stdout.write(base64.b64encode(d[:"
    + str(SCRATCH_READ_MAX_BYTES)
    + "]).decode())\n"
)
# delete/list run as python too: a leading ``python3 -c '<guard>' && rm``
# prefix cannot be expressed in the single-invocation commands the local
# execvp branch of ``_run_remote`` accepts.
# delete is different: os.remove never follows a final-component symlink, so
# the escape vector is a symlinked *parent* directory. Guard the parent's
# realpath and unlink the literal operand — deleting ``/var/tmp/link`` where
# link -> /var/tmp/real must remove the link, not ``real``.
_PY_DELETE = (
    "import os,sys\n"
    f"root=os.path.realpath({SCRATCH_ROOT!r})\n"
    "parent=os.path.realpath(os.path.dirname(sys.argv[1]))\n"
    "if not (parent==root or parent.startswith(root+'/')):\n"
    "    sys.stderr.write('scratch path escapes '+root+': '+sys.argv[1]+' -> '+parent+'\\n')\n"
    "    sys.exit(3)\n"
    "try:\n"
    "    os.remove(sys.argv[1])\n"
    "except FileNotFoundError:\n"
    "    pass\n"
)
_PY_LIST = (
    _PY_GUARD
    + "import os,sys\n"
    + "if os.path.isdir(r):\n"
    + "    names=sorted(os.listdir(r))\n"
    + "    if names: print('\\n'.join(names))\n"
    + "elif os.path.lexists(r):\n"
    + "    print(sys.argv[1])\n"
    + "else:\n"
    + "    sys.exit(2)\n"
)


def _scratch_path(path: str) -> str | None:
    """Normalize ``path`` and return it when it stays beneath ``SCRATCH_ROOT``."""
    if not isinstance(path, str) or not path.strip():
        return None
    norm = posixpath.normpath(path.strip())
    if norm != SCRATCH_ROOT and not norm.startswith(SCRATCH_ROOT + "/"):
        return None
    return norm


def _scratch_write_command(
    qpath: str, content: str | None, content_base64: str | None
) -> tuple[str | None, str | None, str | None]:
    """Build the write command; returns ``(command, stdin_text, error)``.

    The base64 payload goes to the child's stdin (#2505) — never argv.
    """
    if content is not None and content_base64 is not None:
        return None, None, "pass either content or content_base64, not both"
    if content_base64 is not None:
        try:
            data = base64.b64decode(content_base64, validate=True)
        except ValueError:
            return None, None, "content_base64 is not valid base64"
    elif content is not None:
        data = content.encode("utf-8")
    else:
        return None, None, "content or content_base64 is required for action='write'"
    if len(data) > SCRATCH_WRITE_MAX_BYTES:
        return None, None, f"content exceeds {SCRATCH_WRITE_MAX_BYTES} bytes"
    b64 = base64.b64encode(data).decode("ascii")
    return f"python3 -c {shlex.quote(_PY_WRITE)} {qpath}", b64, None


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
    dry_run: Annotated[
        bool,
        Field(description="Show the remote command without executing it (write/delete only)."),
    ] = True,
    confirm: Annotated[
        bool,
        Field(description="Confirm a mutating action (required with dry_run=false for write/delete)."),
    ] = False,
) -> str:
    """Create, read, delete or list scratch files under ``/var/tmp`` on a node.

    Scratch space is where scenario legs stage fixture files (quotes, proofs,
    media) that ``run_aitbc_cli`` then references via ``--*-file`` options or
    ``cwd``/``env`` paths. Paths outside ``/var/tmp`` are refused, so the tool
    cannot touch ``/etc``, ``/var/lib/aitbc`` or user homes.

    ``write`` and ``delete`` mutate node state and require ``dry_run=false``
    plus ``confirm=true`` — the same contract as every other mutating tool.
    ``read`` and ``list`` execute immediately.

    Examples:
      - action="write", path="/var/tmp/s76/quote.json", content='{"price": "1.5"}', dry_run=false, confirm=true
      - action="read", path="/var/tmp/s76/quote.json"
      - action="delete", path="/var/tmp/s76/quote.json", dry_run=false, confirm=true
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
    stdin_text: str | None = None
    if action == "write":
        cmd, stdin_text, error = _scratch_write_command(qpath, content, content_base64)
        if error or cmd is None:
            return _json({"error": error or "failed to build write command"})
        command = cmd
    elif action == "read":
        command = f"python3 -c {shlex.quote(_PY_READ)} {qpath}"
    elif action == "delete":
        command = f"python3 -c {shlex.quote(_PY_DELETE)} {qpath}"
    else:  # list
        command = f"python3 -c {shlex.quote(_PY_LIST)} {qpath}"

    # #2792: write/delete mutate node state (as root over SSH) but ran with no
    # gate at all — every other mutating tool requires dry_run=false +
    # confirm=true. read/list stay immediate.
    if action in ("write", "delete"):
        if dry_run:
            return _json(_build_dry_run("Set dry_run=false and confirm=true to execute.", command, host=target))
        if not confirm:
            return _json(
                {
                    "error": "Confirmation required",
                    "command": command,
                    **_execution_context(target),
                    "note": "Scratch write/delete require dry_run=false and confirm=true.",
                }
            )

    result = _run_remote(target, command, timeout, stdin_text=stdin_text)
    if action == "read":
        result = _scratch_read_result(result)
    result["path"] = norm
    result["action"] = action
    return _json(result)
