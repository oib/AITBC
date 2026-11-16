"""Service-execution handlers for the agent task executor — split out of
``agent_task_executor.py`` (#1860).

This module holds the local service endpoints, the per-service health map,
the IPFS/content helpers used by the handlers, and the whisper / ffmpeg /
ollama-adjacent / ipfs pin service handlers plus ``SERVICE_HANDLERS`` and
``_service_ready``.

Monkeypatch seam: ``agent_task_executor`` keeps the real implementations of
the helpers the tests stub (``_task_max_payload_bytes`` and ``_ipfs_unpin``);
the handlers below reach them through the deferred delegates at the top of
this file, which resolve the attribute on ``agent_task_executor`` at call
time — so ``patch("agent_task_executor.<name>")`` keeps working exactly as
before the split. ``agent_task_executor`` re-exports every moved name, so
``agent_task_executor.<name>`` keeps resolving for callers and tests.
"""

import json
import os
from typing import Any

import requests

import ipfs_pinning_sweeper

from aitbc.aitbc_logging import get_logger

# Same logger name as agent_task_executor so journal lines keep their tag.
logger = get_logger("agent_task_executor")


def _ate():
    """Late import of ``agent_task_executor`` — it imports this module, so the
    reference can only be resolved after both modules are loaded."""
    import agent_task_executor

    return agent_task_executor


def _task_max_payload_bytes() -> int:
    """Deferred delegate to ``agent_task_executor._task_max_payload_bytes``."""
    cap: int = _ate()._task_max_payload_bytes()
    return cap


def _ipfs_unpin(cid: str) -> None:
    """Deferred delegate to ``agent_task_executor._ipfs_unpin``."""
    _ate()._ipfs_unpin(cid)


# Local service endpoints (provider-side execution)
ISLAND_IPFS_API = os.environ.get("ISLAND_IPFS_API", "http://127.0.0.1:5002")
WHISPER_URL = os.environ.get("AGENT_EXECUTOR_WHISPER_URL", "http://127.0.0.1:8110")
FFMPEG_URL = os.environ.get("AGENT_EXECUTOR_FFMPEG_URL", "http://127.0.0.1:8230")
OLLAMA_URL = os.environ.get("AGENT_EXECUTOR_OLLAMA_URL", "http://127.0.0.1:11434")

# Per-service health probes used for the capacity check.
_SERVICE_HEALTH = {
    "whisper": f"{WHISPER_URL}/health",
    "ffmpeg": f"{FFMPEG_URL}/health",
    "ollama": f"{OLLAMA_URL}/api/tags",
    "ipfs": f"{ISLAND_IPFS_API}/api/v0/id",
}


def _require_cid_arg(cid: str) -> None:
    """Reject non-CID payload_ref values before they reach a Kubo arg (#1939).

    Kubo resolves pin/cat/object args as IPFS *paths*, so a buyer-controlled
    ``payload_ref`` containing '/', '..', whitespace or other path syntax could
    steer the daemon at unintended DAGs. Only bare alphanumeric CID spellings
    pass — the same check the pinning sweeper applies (#1582).
    """
    if not ipfs_pinning_sweeper._valid_cid_arg(cid):
        raise ValueError(f"malformed IPFS CID arg: {cid!r}")


def _bounded_content(resp: requests.Response, cap: int) -> bytes:
    """Read a response body with a running byte count — never holds > cap."""
    headers = getattr(resp, "headers", None) or {}
    cl = headers.get("Content-Length")
    try:
        declared = int(cl) if cl is not None else None
    except (TypeError, ValueError):
        declared = None
    if declared is not None and declared > cap:
        raise ValueError(f"response body {cl} bytes exceeds {cap} cap")
    stream = getattr(resp, "iter_content", None)
    if callable(stream):
        buf = bytearray()
        try:
            for chunk in stream(chunk_size=65536):
                buf += chunk
                if len(buf) > cap:
                    raise ValueError(f"response body exceeds {cap} cap")
            return bytes(buf)
        except TypeError:
            pass  # streamless/mocked response — bound on .content instead
    content = resp.content
    if len(content) > cap:
        raise ValueError(f"response body {len(content)} bytes exceeds {cap} cap")
    return content


def _ipfs_object_size(cid: str) -> int | None:
    """Best-effort object size from the daemon; None when unknown."""
    _require_cid_arg(cid)
    try:
        resp = requests.post(f"{ISLAND_IPFS_API}/api/v0/object/stat", params={"arg": cid}, timeout=30)
        if resp.status_code == 200:
            size = resp.json().get("CumulativeSize") or resp.json().get("DataSize")
            return int(size) if size is not None else None
    except (requests.exceptions.RequestException, ValueError, TypeError) as exc:
        logger.debug("ipfs object stat failed for %s: %s", cid, exc)  # cat stream still bounds the read
    return None


def _shop_access_headers(req: dict[str, Any]) -> dict[str, str]:
    """Shop-gate credential headers (#803) carried on the task request (#1612).

    Paid shop endpoints (whisper ``/transcribe``, ffmpeg ``/process``) require
    ``X-Access-Key`` + ``X-Access-Secret`` bound to the market job via
    ``X-Job-Id``. A buyer agent places the credential triple in the
    task_request content — ``access_key``/``access_secret`` plus the market
    job id under ``access_job_id``/``job_id`` — and this executor forwards it
    verbatim; ``task_id`` is the fallback binding. Without it the gated
    service answers 401 and paid A2A work fails. Absent credentials omit the
    headers (the gate's intended refusal for unpaid calls).
    """
    key = req.get("access_key")
    secret = req.get("access_secret")
    if not key or not secret:
        return {}
    bound_job = req.get("access_job_id") or req.get("job_id") or req.get("task_id")
    return {
        "X-Access-Key": str(key),
        "X-Access-Secret": str(secret),
        "X-Job-Id": str(bound_job),
    }


def _exec_whisper(req: dict[str, Any], payload: bytes) -> bytes:
    resp = requests.post(
        f"{WHISPER_URL}/transcribe",
        files={"file": ("audio", payload)},
        data={"task": "transcribe"},
        headers=_shop_access_headers(req),
        timeout=600,
        stream=True,
    )
    resp.raise_for_status()
    return _bounded_content(resp, _task_max_payload_bytes())


def _exec_ffmpeg(req: dict[str, Any], payload: bytes) -> bytes:
    resp = requests.post(
        f"{FFMPEG_URL}/process",
        files={"file": ("input", payload)},
        data={"output_format": "mp4", "codec": "h264"},
        headers=_shop_access_headers(req),
        timeout=1800,
        stream=True,
    )
    resp.raise_for_status()
    return _bounded_content(resp, _task_max_payload_bytes())


def _exec_ipfs(req: dict[str, Any], payload: bytes) -> bytes:
    """IPFS "hosting" task: pin the request's payload CID on the island daemon.

    The CID is buyer-chosen and usually not local yet, so ``object/stat``
    cannot size it before the fetch — ``pin/add`` pulls the whole DAG. Mirror
    the market sweeper's measure-then-reclaim (#1489): pin, stat the now-local
    root, and unpin immediately when the object exceeds the payload cap rather
    than leaving unbounded disk committed (#1614). The per-buyer cumulative
    quota is enforced by the caller, which knows the quoting buyer.
    """
    cid = str(req.get("payload_ref") or "")
    if not cid:
        raise ValueError("ipfs task requires payload_ref (CID)")
    _require_cid_arg(cid)
    resp = requests.post(f"{ISLAND_IPFS_API}/api/v0/pin/add", params={"arg": cid}, timeout=120)
    resp.raise_for_status()
    size = _ipfs_object_size(cid)
    cap = _task_max_payload_bytes()
    if size is not None and size > cap:
        _ipfs_unpin(cid)
        raise ValueError(f"IPFS object {cid} is {size} bytes, over the {cap} cap — pin reclaimed")
    return json.dumps({"pinned": cid, "size": size}).encode()


def _service_ready(service_type: str) -> bool:
    url = _SERVICE_HEALTH.get(service_type)
    if not url:
        return False
    try:
        if service_type in ("ipfs",):
            resp = requests.post(url, timeout=5)
        else:
            resp = requests.get(url, timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False
