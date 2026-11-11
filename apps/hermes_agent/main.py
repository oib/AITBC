"""
AITBC Hermes Agent software offer service.

Exposes a FastAPI HTTP wrapper around the `hermes` CLI one-shot mode.
The shop node provides the Hermes binary, configuration, and API keys.
Buyers pay per minute of wall-clock execution time.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import signal
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from typing import Any

import uvicorn  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.health_checks import create_simple_health_response  # noqa: E402
from aitbc.shop_gate import require_job_access  # noqa: E402
from aitbc.utils.env import subprocess_env  # noqa: E402

configure_logging(level="INFO", service_name="hermes-agent", to_file=True)
logger = get_logger(__name__)

_HERMES_PATH: str | None = None
_HERMES_VERSION: str | None = None

# Shop-controlled defaults and allowlists.  These are read from the systemd
# EnvironmentFile /etc/aitbc/hermes.env or the node.env file, never from the
# buyer's request.
_HERMES_DEFAULT_MODEL = os.getenv("HERMES_DEFAULT_MODEL", "")
_HERMES_DEFAULT_PROVIDER = os.getenv("HERMES_DEFAULT_PROVIDER", "")
_HERMES_DEFAULT_REASONING = os.getenv("HERMES_DEFAULT_REASONING", "medium")
_HERMES_DEFAULT_TOOLSETS = os.getenv("HERMES_DEFAULT_TOOLSETS", "")
_HERMES_ALLOWED_MODELS = [m.strip() for m in os.getenv("HERMES_ALLOWED_MODELS", "").split(",") if m.strip()]
_HERMES_ALLOWED_PROVIDERS = [p.strip() for p in os.getenv("HERMES_ALLOWED_PROVIDERS", "").split(",") if p.strip()]
_HERMES_ALLOWED_TOOLSETS = [t.strip() for t in os.getenv("HERMES_ALLOWED_TOOLSETS", "").split(",") if t.strip()]
_HERMES_MAX_TIME_DEFAULT = int(os.getenv("HERMES_MAX_TIME_DEFAULT", "300"))
_HERMES_MAX_TIME_LIMIT = int(os.getenv("HERMES_MAX_TIME_LIMIT", "3600"))
# HERMES-RUN-SERVICE-HARDENING-1 (#808): /run answers with no credential today; when
# HERMES_RUN_API_KEY is set every /run request must carry it in X-API-Key, the toolset
# fallthrough below stops leaking the full profile, and a semaphore caps parallel runs.
_HERMES_RUN_API_KEY = os.getenv("HERMES_RUN_API_KEY", "")
_HERMES_RUN_MAX_CONCURRENT = int(os.getenv("HERMES_RUN_MAX_CONCURRENT", "4"))
_run_semaphore = asyncio.Semaphore(_HERMES_RUN_MAX_CONCURRENT)
_CONSERVATIVE_TOOLSETS = "web,memory,todo"
# Post-kill drain bound (#1473): after the process group is SIGKILLed, a
# descendant that escaped the group (setsid / double-fork) can keep the
# stdout/stderr pipes open and stretch communicate() — and the enforced
# max_time bound — arbitrarily. The 504 path discards the output anyway, so
# the drain only needs to last long enough to collect whatever the kill
# flushed.
_POST_KILL_DRAIN_SECONDS = float(os.getenv("HERMES_KILL_DRAIN_SECONDS", "10"))
# HERMES-OUT-1 (#1666) / HERMES-RESIDUAL-1 (#1683): stdout/stderr are drained
# continuously (so the child never blocks on a full pipe) but only the first
# _HERMES_MAX_OUTPUT_BYTES of each stream are retained; the rest is counted
# and flagged as truncated. Without a cap, communicate() buffers the child's
# entire output in RAM and _HERMES_RUN_MAX_CONCURRENT parallel runs turn a
# runaway hermes into a memory-exhaustion path.
_HERMES_MAX_OUTPUT_BYTES = int(os.getenv("HERMES_MAX_OUTPUT_BYTES", str(4 * 1024 * 1024)))
# usage-file passthrough guard (#1666): hermes writes this file, but cap what
# we are willing to slurp into memory before json.load.
_USAGE_FILE_MAX_BYTES = 256 * 1024


async def _require_run_credential(request: Request) -> None:
    """Reject /run without the shared secret when one is configured (constant-time compare)."""
    if not _HERMES_RUN_API_KEY:
        return
    token = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(token, _HERMES_RUN_API_KEY):
        raise HTTPException(status_code=401, detail="invalid or missing run credential")


_HERMES_HOME = os.getenv("HERMES_HOME", "/var/lib/aitbc/hermes")

_REASONING_LEVELS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}


def _find_hermes() -> str | None:
    """Return the absolute path to the hermes binary."""
    path = shutil.which(os.getenv("HERMES_BIN", "hermes"))
    if path and os.access(path, os.X_OK):
        return path
    # Common installation locations for Nous Hermes Agent
    for candidate in ("/usr/local/bin/hermes", "/opt/aitbc/venv/bin/hermes", os.path.expanduser("~/.local/bin/hermes")):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


async def _discover_version() -> str | None:
    """Try to discover the hermes version once at startup."""
    if not _HERMES_PATH:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            _HERMES_PATH,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=subprocess_env(),
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=10)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        stdout = out_b.decode(errors="replace")
        stderr = err_b.decode(errors="replace")
        # The first line contains the version, e.g. "Hermes Agent v0.20.4 ..."
        first = stdout.strip().splitlines()[0] if stdout.strip() else ""
        if first:
            return first
        if stderr.strip():
            return stderr.strip().splitlines()[0]
    except Exception as e:
        logger.warning("Could not determine hermes version: %s", e)
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: locate hermes and pre-discover version if possible."""
    global _HERMES_PATH, _HERMES_VERSION
    _HERMES_PATH = _find_hermes()
    if _HERMES_PATH:
        _HERMES_VERSION = await _discover_version()
        logger.info("Hermes agent service ready: %s", _HERMES_VERSION or _HERMES_PATH)
    else:
        logger.error("hermes binary not found in PATH")
    yield
    _HERMES_PATH = None
    _HERMES_VERSION = None


app = FastAPI(title="AITBC Hermes Agent Service", version="1.0.0", lifespan=lifespan)


class HermesRunRequest(BaseModel):
    """One-shot Hermes execution request."""

    prompt: str = Field(..., min_length=1, max_length=100000, description="Prompt to send to Hermes")
    max_time: int = Field(
        default=_HERMES_MAX_TIME_DEFAULT,
        ge=1,
        le=_HERMES_MAX_TIME_LIMIT,
        description="Maximum wall-clock execution time in seconds",
    )
    model: str | None = Field(default=None, description="Optional model override")
    provider: str | None = Field(default=None, description="Optional provider override")
    reasoning: str | None = Field(default=None, description="Optional reasoning effort level")
    toolsets: str | None = Field(default=None, description="Optional comma-separated toolsets")


@app.get("/health")
async def health():
    """Health check: service is ready when the hermes binary is found."""
    return create_simple_health_response(
        "hermes_agent",
        status="ok" if _HERMES_PATH else "error",
        ready=_HERMES_PATH is not None,
        version=_HERMES_VERSION,
        default_model=_HERMES_DEFAULT_MODEL or "unset",
        default_provider=_HERMES_DEFAULT_PROVIDER or "unset",
        default_reasoning=_HERMES_DEFAULT_REASONING,
        default_toolsets=_HERMES_DEFAULT_TOOLSETS or "unset",
        max_time_default=_HERMES_MAX_TIME_DEFAULT,
        max_time_limit=_HERMES_MAX_TIME_LIMIT,
    )


@app.get("/capabilities")
async def capabilities():
    """Return safe, non-secret configuration for buyers."""
    return {
        "service": "hermes",
        "version": _HERMES_VERSION,
        "default_model": _HERMES_DEFAULT_MODEL or None,
        "default_provider": _HERMES_DEFAULT_PROVIDER or None,
        "default_reasoning": _HERMES_DEFAULT_REASONING,
        "default_toolsets": _HERMES_DEFAULT_TOOLSETS or None,
        "allowed_models": _HERMES_ALLOWED_MODELS or None,
        "allowed_providers": _HERMES_ALLOWED_PROVIDERS or None,
        "allowed_toolsets": _HERMES_ALLOWED_TOOLSETS or None,
        "max_time_default": _HERMES_MAX_TIME_DEFAULT,
        "max_time_limit": _HERMES_MAX_TIME_LIMIT,
    }


async def _communicate_bounded(proc: asyncio.subprocess.Process, limit: int) -> tuple[bytes, bytes, bool, bool]:
    """Drain stdout+stderr concurrently, retaining at most ``limit`` bytes each.

    Returns ``(stdout, stderr, stdout_truncated, stderr_truncated)``. Unlike
    ``proc.communicate()`` the retained memory is bounded by ``limit`` per
    stream regardless of how much the child writes.
    """

    out_stream = proc.stdout
    err_stream = proc.stderr
    if out_stream is None or err_stream is None:
        raise RuntimeError("hermes subprocess pipes missing")

    async def _drain(stream: asyncio.StreamReader) -> tuple[bytes, bool]:
        kept = bytearray()
        total = 0
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                break
            total += len(chunk)
            remaining = limit - len(kept)
            if remaining > 0:
                kept += chunk[:remaining]
        return bytes(kept), total > limit

    # Drain both pipes concurrently: a sequential read can deadlock when the
    # child fills the unread pipe's buffer while we wait on the other.
    (out_b, out_trunc), (err_b, err_trunc) = await asyncio.gather(_drain(out_stream), _drain(err_stream))
    return out_b, err_b, out_trunc, err_trunc


def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
    """SIGKILL the child's whole process group (it is a session leader)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()  # noqa: unawaited-async — Process.kill() is synchronous
        except ProcessLookupError:
            pass


async def _reap_after_kill(proc: asyncio.subprocess.Process) -> None:
    """Bounded wait for the killed child to be reaped.

    ``proc.wait()`` only waits on the direct child — a descendant that
    escaped the process group (setsid/double-fork) keeps the pipes open but
    cannot stretch this wait. Any cancellation delivered while reaping is
    swallowed: the caller is already on a kill path and the child watcher
    reaps the child even if we stop awaiting it.
    """
    try:
        await asyncio.wait_for(proc.wait(), timeout=_POST_KILL_DRAIN_SECONDS)
    except BaseException:  # noqa: BLE001 — TimeoutError and re-delivered CancelledError both fine here
        logger.warning("post-kill reap timed out or was cancelled for pid %s", proc.pid)


def _build_command(request: HermesRunRequest, usage_path: str) -> list[str]:
    """Build the hermes one-shot command from the request and shop defaults."""
    if not _HERMES_PATH:
        raise HTTPException(status_code=503, detail="Hermes binary is not available")

    command = [_HERMES_PATH, "-z", request.prompt, "--usage-file", usage_path]

    # HERMES-IPFS-DEPTH2-1 (#1633): an empty allowlist means "default only"
    # (README), not "unrestricted" — resolve the effective allowed set once so
    # a buyer-supplied value can never widen past the shop's configured
    # defaults when no allowlist is set.
    allowed_models = _HERMES_ALLOWED_MODELS or ([_HERMES_DEFAULT_MODEL] if _HERMES_DEFAULT_MODEL else [])
    allowed_providers = _HERMES_ALLOWED_PROVIDERS or ([_HERMES_DEFAULT_PROVIDER] if _HERMES_DEFAULT_PROVIDER else [])
    # HERMES-ALLOWLIST-1 (#1804): an empty resolved allow set is not allow-all —
    # omitting --model/--provider/--toolsets would fall through to Hermes defaults.
    if not allowed_models:
        raise HTTPException(status_code=503, detail="Models are not configured for this offer")
    if not allowed_providers:
        raise HTTPException(status_code=503, detail="Providers are not configured for this offer")

    model = request.model or _HERMES_DEFAULT_MODEL
    if model:
        if model not in allowed_models:
            raise HTTPException(status_code=400, detail=f"Model '{model}' is not allowed by this offer")
        command.extend(["--model", model])

    provider = request.provider or _HERMES_DEFAULT_PROVIDER
    if provider:
        if provider not in allowed_providers:
            raise HTTPException(status_code=400, detail=f"Provider '{provider}' is not allowed by this offer")
        command.extend(["--provider", provider])

    reasoning = request.reasoning or _HERMES_DEFAULT_REASONING
    if reasoning:
        if reasoning.lower() not in _REASONING_LEVELS:
            raise HTTPException(status_code=400, detail=f"Invalid reasoning level '{reasoning}'")
        command.extend(["--reasoning", reasoning.lower()])

    raw = request.toolsets if request.toolsets is not None else _HERMES_DEFAULT_TOOLSETS
    requested = [t.strip() for t in (raw or "").split(",") if t.strip()]
    if request.toolsets is not None and not requested:
        # '', ',' or ' , ' means "use the default", not "run unrestricted".
        requested = [t.strip() for t in _HERMES_DEFAULT_TOOLSETS.split(",") if t.strip()]
    # HERMES-IPFS-DEPTH2-1 (#1633): empty allowlist falls back to the default
    # toolsets as the allowed set — a non-empty request can never pass
    # toolsets the shop did not configure.
    allowed_toolsets = _HERMES_ALLOWED_TOOLSETS or [t.strip() for t in _HERMES_DEFAULT_TOOLSETS.split(",") if t.strip()]
    if not allowed_toolsets:
        raise HTTPException(status_code=503, detail="Toolsets are not configured for this offer")
    for t in requested:
        if t not in allowed_toolsets:
            raise HTTPException(status_code=400, detail=f"Toolset '{t}' is not allowed by this offer")
    if not requested:
        # Nothing requested and no default: never fall through to hermes'
        # full profile — emit the conservative set bounded by the allowlist.
        requested = [t for t in (x.strip() for x in _CONSERVATIVE_TOOLSETS.split(",")) if t in allowed_toolsets] or list(
            allowed_toolsets
        )
    if requested:
        command.extend(["--toolsets", ",".join(requested)])

    return command


@app.post("/run", dependencies=[Depends(require_job_access)])
async def run_hermes(request: HermesRunRequest, _cred: None = Depends(_require_run_credential)):
    """Run a one-shot Hermes prompt and return the result plus timing."""
    await _run_semaphore.acquire()
    try:
        return await _run_hermes_inner(request)
    finally:
        _run_semaphore.release()  # noqa: unawaited-async — Semaphore.release() is synchronous


async def _run_hermes_inner(request: HermesRunRequest):
    # Use a temporary working directory to avoid loading AGENTS.md/skills from the
    # service source tree.  Hermes still reads HERMES_HOME for config and env.
    with tempfile.TemporaryDirectory(prefix="hermes_run_") as tmpdir:
        usage_fd, usage_path = tempfile.mkstemp(prefix="hermes_usage_", suffix=".json", dir=tmpdir)
        os.close(usage_fd)  # noqa: unawaited-async — os.close() is synchronous
        command = _build_command(request, usage_path)

        t_start = time.time()
        # Async subprocess keeps the event loop free for the duration of the
        # run (up to max_time) so /health stays responsive; on timeout the
        # child is killed and whatever output it produced is still collected.
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=tmpdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        output_truncated = False
        try:
            out_b, err_b, out_trunc, err_trunc = await asyncio.wait_for(
                _communicate_bounded(proc, _HERMES_MAX_OUTPUT_BYTES), timeout=request.max_time
            )
            output_truncated = out_trunc or err_trunc
        except TimeoutError:
            # The child is a session leader (start_new_session=True), so its
            # pid is also its process-group id. Killing only the direct child
            # leaves tool subprocesses alive holding the stdout/stderr pipes —
            # a naive communicate() would then block until THEY exit, stretching
            # the enforced max_time bound arbitrarily (#1473).
            _kill_process_group(proc)
            # Bounded reap: killpg covers the process group, but a descendant
            # that escaped it (setsid / double-fork) keeps running — there is
            # no cgroup containment (#1683 item 3, needs a design decision).
            # proc.wait() only waits on the direct child, so the escapee
            # cannot stretch this either; the 504 below discards output anyway.
            await _reap_after_kill(proc)
            out_b, err_b = b"", b""
            timed_out = True
        except asyncio.CancelledError:
            # HERMES-RESIDUAL-1 (#1683): a client disconnect or service shutdown
            # cancels this task — without an explicit kill the hermes child
            # keeps running detached in its own session with NO timeout.
            _kill_process_group(proc)
            await _reap_after_kill(proc)
            raise
        except BaseException:
            # Any other failure mid-run (e.g. pipe error) must not leak the
            # child either — same kill+reap, then propagate.
            _kill_process_group(proc)
            await _reap_after_kill(proc)
            raise
        # HERMES-IPFS-DEPTH2-1 (#1633): communicate() returning only proves the
        # pipe-holding processes exited — a grandchild that detached its fds
        # (redirected stdout/stderr) survives in the group on the success and
        # non-zero-exit paths too. killpg is harmless when the group is already
        # gone (ProcessLookupError) and the pgid cannot be recycled while a
        # member still lives, so sweep it on every exit path.
        _kill_process_group(proc)
        elapsed = time.time() - t_start
        stdout = out_b.decode(errors="replace")
        stderr = err_b.decode(errors="replace")
        returncode = -1 if timed_out else (proc.returncode or 0)

        # Try to read usage report if it was produced. Cap the slurp
        # (#1666): the file is written by the shop-controlled hermes binary,
        # but an oversized or malformed file must not be loaded wholesale.
        usage: dict[str, Any] = {}
        try:
            if os.path.getsize(usage_path) <= _USAGE_FILE_MAX_BYTES:
                with open(usage_path) as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    usage = loaded
        except Exception:
            pass

    if timed_out:
        raise HTTPException(
            status_code=504,
            detail="Hermes run exceeded max_time of " + str(request.max_time) + "s",
        )

    if returncode != 0:
        logger.warning("Hermes exited with code %s: %s", returncode, stderr[:500])
        raise HTTPException(
            status_code=502,
            detail="Hermes run failed (exit " + str(returncode) + ")",
        )

    result_text = stdout.strip()
    result_hash = hashlib.sha256(result_text.encode()).hexdigest()
    elapsed_rounded = round(elapsed, 2)
    duration_minutes = round(elapsed / 60, 4)

    return JSONResponse(
        {
            "text": result_text,
            "status": "completed",
            "output_truncated": output_truncated,
            "elapsed_seconds": elapsed_rounded,
            "duration_minutes": duration_minutes,
            "result_hash": result_hash,
            "model": request.model or _HERMES_DEFAULT_MODEL or None,
            "provider": request.provider or _HERMES_DEFAULT_PROVIDER or None,
            "reasoning": request.reasoning or _HERMES_DEFAULT_REASONING,
            "toolsets": request.toolsets or _HERMES_DEFAULT_TOOLSETS or None,
            "usage": usage,
        }
    )


if __name__ == "__main__":
    # code default only; the effective bind is pinned per host in the systemd unit. the containers run no firewall of their own, so a bind-all default is reachable by every other container on the bridge; accepted deviation tracked in docs/deployment/NETWORK_POLICY.md, not a safe fallback
    host = os.getenv("HERMES_BIND_HOST", "0.0.0.0")  # nosec B104
    port = int(os.getenv("HERMES_BIND_PORT", os.getenv("HERMES_PORT", "8270")))
    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
