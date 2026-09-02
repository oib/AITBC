"""
AITBC Hermes Agent software offer service.

Exposes a FastAPI HTTP wrapper around the `hermes` CLI one-shot mode.
The shop node provides the Hermes binary, configuration, and API keys.
Buyers pay per minute of wall-clock execution time.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from typing import Any

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.health_checks import create_simple_health_response  # noqa: E402

configure_logging(level="INFO", service_name="hermes_agent", to_file=True)
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


def _discover_version() -> str | None:
    """Try to discover the hermes version once at startup."""
    if not _HERMES_PATH:
        return None
    try:
        result = subprocess.run(
            [_HERMES_PATH, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        # The first line contains the version, e.g. "Hermes Agent v0.20.4 ..."
        first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if first:
            return first
        if result.stderr.strip():
            return result.stderr.strip().splitlines()[0]
    except Exception as e:
        logger.warning("Could not determine hermes version: %s", e)
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: locate hermes and pre-discover version if possible."""
    global _HERMES_PATH, _HERMES_VERSION
    _HERMES_PATH = _find_hermes()
    if _HERMES_PATH:
        _HERMES_VERSION = _discover_version()
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


def _build_command(request: HermesRunRequest, usage_path: str) -> list[str]:
    """Build the hermes one-shot command from the request and shop defaults."""
    if not _HERMES_PATH:
        raise HTTPException(status_code=503, detail="Hermes binary is not available")

    command = [_HERMES_PATH, "-z", request.prompt, "--usage-file", usage_path]

    model = request.model or _HERMES_DEFAULT_MODEL
    if model:
        if _HERMES_ALLOWED_MODELS and model not in _HERMES_ALLOWED_MODELS:
            raise HTTPException(status_code=400, detail=f"Model '{model}' is not allowed by this offer")
        command.extend(["--model", model])

    provider = request.provider or _HERMES_DEFAULT_PROVIDER
    if provider:
        if _HERMES_ALLOWED_PROVIDERS and provider not in _HERMES_ALLOWED_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Provider '{provider}' is not allowed by this offer")
        command.extend(["--provider", provider])

    reasoning = request.reasoning or _HERMES_DEFAULT_REASONING
    if reasoning:
        if reasoning.lower() not in _REASONING_LEVELS:
            raise HTTPException(status_code=400, detail=f"Invalid reasoning level '{reasoning}'")
        command.extend(["--reasoning", reasoning.lower()])

    toolsets = request.toolsets or _HERMES_DEFAULT_TOOLSETS
    if toolsets:
        requested = [t.strip() for t in toolsets.split(",") if t.strip()]
        if _HERMES_ALLOWED_TOOLSETS:
            for t in requested:
                if t not in _HERMES_ALLOWED_TOOLSETS:
                    raise HTTPException(status_code=400, detail=f"Toolset '{t}' is not allowed by this offer")
        if requested:
            command.extend(["--toolsets", ",".join(requested)])

    return command


@app.post("/run")
async def run_hermes(request: HermesRunRequest):
    """Run a one-shot Hermes prompt and return the result plus timing."""
    # Use a temporary working directory to avoid loading AGENTS.md/skills from the
    # service source tree.  Hermes still reads HERMES_HOME for config and env.
    with tempfile.TemporaryDirectory(prefix="hermes_run_") as tmpdir:
        usage_fd, usage_path = tempfile.mkstemp(prefix="hermes_usage_", suffix=".json", dir=tmpdir)
        os.close(usage_fd)
        command = _build_command(request, usage_path)

        t_start = time.time()
        try:
            result = subprocess.run(
                command,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=request.max_time,
                start_new_session=True,
            )
            elapsed = time.time() - t_start
            stdout = result.stdout
            stderr = result.stderr
            returncode = result.returncode
            timed_out = False
        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - t_start
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            returncode = -1
            timed_out = True

        # Try to read usage report if it was produced
        usage: dict[str, Any] = {}
        try:
            with open(usage_path) as f:
                usage = json.load(f)
        except Exception:
            pass

    if timed_out:
        raise HTTPException(
            status_code=504,
            detail=f"Hermes run exceeded max_time of {request.max_time}s",
        )

    if returncode != 0:
        logger.warning("Hermes exited with code %s: %s", returncode, stderr[:500])
        raise HTTPException(
            status_code=502,
            detail=f"Hermes run failed (exit {returncode}): {stderr[:1000]}",
        )

    result_text = stdout.strip()
    result_hash = hashlib.sha256(result_text.encode()).hexdigest()
    elapsed_rounded = round(elapsed, 2)
    duration_minutes = round(elapsed / 60, 4)

    return JSONResponse(
        {
            "text": result_text,
            "status": "completed",
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
    host = os.getenv("HERMES_BIND_HOST", "0.0.0.0")  # nosec B104 - systemd-only service; boundary is firewall/reverse-proxy
    port = int(os.getenv("HERMES_BIND_PORT", os.getenv("HERMES_PORT", "8270")))
    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
