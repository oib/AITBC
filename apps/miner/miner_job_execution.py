"""Job-execution phase for the production miner — split out of
``production_miner.py`` (#1860).

This module holds the media-download bounds/helpers, payload-name guards,
the per-type job executors (inference / transcribe / reencode / gpu_compute)
and the GPU-rental duration/deadline helpers.

Monkeypatch seam: ``production_miner`` keeps the real implementations of
every leaf the tests stub (``_download_media``, ``_run_whisper``,
``_run_ffmpeg``, ``_submit_success``, ``_submit_failure``, ``_gpu_snapshot``,
``build_tee_quote``) plus ``AITBCHTTPClient``. The executors below call those
names through the deferred delegates at the top of this file, which resolve
the attribute on ``production_miner`` at call time — so
``patch("production_miner.<name>")`` keeps working exactly as before the
split. ``production_miner`` re-exports every moved name, so
``production_miner.<name>`` keeps resolving for callers and tests.
"""

import base64
import ipaddress
import json
import math
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.parse
from datetime import UTC, datetime
from typing import Any

import requests

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError
from aitbc.zk_model_circuits import ModelCircuit, get_model, text_to_field_array

# Same logger name as production_miner so journal lines keep their tag.
logger = get_logger("production_miner")


def _pm():
    """Late import of ``production_miner`` — it imports this module, so the
    reference can only be resolved after both modules are loaded."""
    import production_miner

    return production_miner


def _download_media(url: str, dest: str) -> None:
    """Deferred delegate to ``production_miner._download_media``."""
    _pm()._download_media(url, dest)


def _run_whisper(*args: Any, **kwargs: Any) -> Any:
    """Deferred delegate to ``production_miner._run_whisper``."""
    return _pm()._run_whisper(*args, **kwargs)


def _run_ffmpeg(*args: Any, **kwargs: Any) -> Any:
    """Deferred delegate to ``production_miner._run_ffmpeg``."""
    return _pm()._run_ffmpeg(*args, **kwargs)


def _submit_success(*args: Any, **kwargs: Any) -> Any:
    """Deferred delegate to ``production_miner._submit_success``."""
    return _pm()._submit_success(*args, **kwargs)


def _submit_failure(*args: Any, **kwargs: Any) -> Any:
    """Deferred delegate to ``production_miner._submit_failure``."""
    return _pm()._submit_failure(*args, **kwargs)


def _gpu_snapshot() -> dict[str, Any]:
    """Deferred delegate to ``production_miner._gpu_snapshot``."""
    snapshot: dict[str, Any] = _pm()._gpu_snapshot()
    return snapshot


def build_tee_quote(*args: Any, **kwargs: Any) -> Any:
    """Deferred delegate to ``production_miner.build_tee_quote``."""
    return _pm().build_tee_quote(*args, **kwargs)


def AITBCHTTPClient(*args: Any, **kwargs: Any) -> Any:
    """Deferred delegate to ``production_miner.AITBCHTTPClient`` — tests patch
    the class attribute on that module."""
    return _pm().AITBCHTTPClient(*args, **kwargs)


# Miner failure surface: job-execution handlers, nvidia-smi subprocess probes,
# coordinator HTTP polling, TEE quote generation, and the data-shape errors
# job payloads can raise.
_OPS_ERRORS = (
    AITBCError,
    requests.exceptions.RequestException,
    OSError,
    subprocess.SubprocessError,
    TimeoutError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ArithmeticError,
    LookupError,
)


# Media download bounds (#800): job payloads are buyer-controlled, so the
# fetch must refuse non-public targets and stop at a byte cap + deadline.
_MEDIA_MAX_BYTES_ENV = "MINER_MEDIA_MAX_BYTES"
_MEDIA_DEFAULT_MAX_BYTES = 512 * 1024 * 1024  # sized to the ffmpeg upload limit
_MEDIA_MAX_REDIRECTS = 5
_MEDIA_TOTAL_DEADLINE_S = 600


def _media_max_bytes() -> int:
    try:
        return max(1, int(os.environ.get(_MEDIA_MAX_BYTES_ENV, _MEDIA_DEFAULT_MAX_BYTES)))
    except ValueError:
        return _MEDIA_DEFAULT_MAX_BYTES


# ffmpeg output bound (#1932 F7): mirrors the ffmpeg service's ``-fs`` cap —
# bitrate is bounded but duration is not, so without it a long input writes
# an unbounded file. The service default is FFMPEG_MAX_OUTPUT_MB=4096; the
# miner keeps the same default under its own env name.
_FFMPEG_MAX_OUTPUT_MB_ENV = "MINER_FFMPEG_MAX_OUTPUT_MB"
_FFMPEG_DEFAULT_MAX_OUTPUT_BYTES = 4096 * 1024 * 1024


def _ffmpeg_max_output_bytes() -> int:
    try:
        return max(1, int(os.environ.get(_FFMPEG_MAX_OUTPUT_MB_ENV, "4096"))) * 1024 * 1024
    except ValueError:
        return _FFMPEG_DEFAULT_MAX_OUTPUT_BYTES


# Inference read timeout (#2294): 180s was fine for warm GPU ollama but CPU-only
# nodes cold-load the model and serialize concurrent jobs, so a single generate
# call can legitimately exceed it — the miner then reports FAILURE and the
# buyer's escrow has to be swept. Env-tunable; 600s bounds a wedged ollama
# without failing slow-but-healthy CPU inference.
_OLLAMA_TIMEOUT_ENV = "MINER_OLLAMA_TIMEOUT_SECONDS"
_OLLAMA_DEFAULT_TIMEOUT_SECONDS = 600


def _ollama_timeout_seconds() -> int:
    try:
        return max(1, int(os.environ.get(_OLLAMA_TIMEOUT_ENV, _OLLAMA_DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        return _OLLAMA_DEFAULT_TIMEOUT_SECONDS


def _check_media_url(url: str) -> urllib.parse.ParseResult:
    """Refuse http(s) URLs whose host resolves to any non-public address —
    loopback, private, link-local, metadata, multicast. Called per hop, so a
    redirect to a non-public target is refused the same way."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"media URL host does not resolve: {host}: {e}") from e
    if not infos:
        raise ValueError(f"media URL host does not resolve: {host}")
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            raise ValueError(f"media URL host resolves to a non-public address: {addr}")
    return parsed


def _write_data_uri(parsed: urllib.parse.ParseResult, dest: str, cap: int) -> None:
    # data:[<mediatype>][;base64],<data>
    header, _, data = parsed.path.partition(",")
    if ";base64" in header:
        if len(data) * 3 // 4 > cap:
            raise ValueError(f"media exceeds {cap} bytes")
        content = base64.b64decode(data)
    else:
        content = urllib.parse.unquote_to_bytes(data)
    if len(content) > cap:
        raise ValueError(f"media exceeds {cap} bytes")
    with open(dest, "wb") as f:
        f.write(content)


def _stream_to_file(resp: requests.Response, dest: str, cap: int, deadline: float) -> None:
    """Write a response body to *dest*, aborting past *cap* or *deadline*;
    a partial file is removed."""
    written = 0
    try:
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                written += len(chunk)
                if written > cap:
                    raise ValueError(f"media exceeds {cap} bytes")
                if time.monotonic() > deadline:
                    raise ValueError("media download deadline exceeded")
                f.write(chunk)
    except Exception:
        try:
            os.unlink(dest)
        except OSError:
            pass
        raise


def _fetch_http_media(url: str, dest: str, cap: int, deadline: float) -> None:
    """GET *url* to *dest*, following at most _MEDIA_MAX_REDIRECTS hops with
    the public-address check re-run on each."""
    url_now = url
    for _ in range(_MEDIA_MAX_REDIRECTS + 1):
        _check_media_url(url_now)
        with requests.get(url_now, timeout=(10, 30), stream=True, allow_redirects=False) as resp:
            if resp.is_redirect or resp.is_permanent_redirect:
                location = resp.headers.get("Location")
                if not location:
                    raise ValueError("redirect without Location")
                url_now = urllib.parse.urljoin(url_now, location)
                continue
            resp.raise_for_status()
            _stream_to_file(resp, dest, cap, deadline)
            return
    raise ValueError(f"too many redirects (>{_MEDIA_MAX_REDIRECTS})")


# Buyer-controlled payload strings that end up in local file paths or ffmpeg
# arguments must match this shape — anything else is a job failure, not a path
# (#1483). Covers output_format and the derived file extension.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")


def _safe_name(value: str | None, default: str) -> str:
    """Return *value* when it is a plain alphanumeric token, else *default*."""
    candidate = (value or "").lstrip(".")
    return candidate if _SAFE_NAME_RE.match(candidate) else default


def _require_safe_name(value: str | None, field: str) -> str:
    """Return *value* when safe, else raise — used where a wrong value is a job bug."""
    candidate = (value or "").strip()
    if not _SAFE_NAME_RE.match(candidate):
        raise RuntimeError(f"Invalid {field} {value!r}: must be 1-16 alphanumeric characters")
    return candidate


def _shop_access_headers(payload: dict[str, Any], job_id) -> dict[str, str]:
    """Shop-gate credential headers (#803) forwarded from the job payload (#1612).

    Paid shop endpoints (whisper ``/transcribe``, ffmpeg ``/process``) require
    ``X-Access-Key`` + ``X-Access-Secret`` bound to the market job via
    ``X-Job-Id``. The buyer places the credential triple in the job payload —
    ``access_key``/``access_secret`` plus the market job id under
    ``access_job_id``/``market_job_id``/``job_id`` — and this miner forwards
    it verbatim. Without it the gated service answers 401 and paid work
    fails. Absent credentials simply omit the headers (the gate's intended
    refusal for unpaid calls).
    """
    key = payload.get("access_key")
    secret = payload.get("access_secret")
    if not key or not secret:
        return {}
    bound_job = payload.get("access_job_id") or payload.get("market_job_id") or payload.get("job_id") or job_id
    return {
        "X-Access-Key": str(key),
        "X-Access-Secret": str(secret),
        "X-Job-Id": str(bound_job),
    }


def execute_job(job, available_models):
    """Execute a job using real GPU resources"""
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    logger.info("Executing job %s: %s", job_id, payload)
    job_type = payload.get("type")
    # Market/CLI may submit plugin-style types; map them to the worker's
    # canonical task handlers.
    _TYPE_ALIASES = {
        "ollama": "inference",
        "llama": "inference",
        "whisper": "transcribe",
        "ffmpeg": "reencode",
    }
    if job_type in _TYPE_ALIASES:
        job_type = _TYPE_ALIASES[job_type]
    if job_type is None and "model" in payload and ("prompt" in payload):
        job_type = "inference"

    try:
        if job_type == "inference":
            return _execute_inference(job, available_models)
        if job_type == "transcribe":
            return _execute_transcribe(job)
        if job_type == "reencode":
            return _execute_reencode(job)
        if job_type == "gpu_compute":
            return _execute_gpu_compute(job)
        logger.error("Unsupported job type: %s", job_type)
        _submit_failure(job_id, f"Unsupported job type: {job_type}")
        return False
    except _OPS_ERRORS as e:
        logger.error("Job execution error: %s", e)
        _submit_failure(job_id, str(e))
        return False


def _execute_inference(job, available_models):
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    prompt = payload.get("prompt", "")
    # #1788: an explicitly requested model must run or the job must fail —
    # silently substituting a different model bills the buyer for capability
    # they did not ask for. Only an *unspecified* model falls back.
    requested_model = payload.get("model")
    if requested_model:
        model = requested_model
        # #2330: a registered ZK circuit model (e.g. linear-1) is not an Ollama
        # model — it executes locally as a deterministic field computation. The
        # coordinator generates the Groth16 receipt_model proof itself and
        # ignores the output values, but the miner must still run the circuit
        # and return a result for the job to COMPLETE.
        circuit = get_model(model)
        if circuit is not None:
            return _execute_circuit_model(job, circuit)
        if model not in available_models:
            raise RuntimeError(f"Requested model '{model}' is not available on this miner")
    else:
        model = "llama3.2:latest"
        if model not in available_models:
            if available_models:
                model = available_models[0]
                logger.info("Default model unavailable; using available model: %s", model)
            else:
                raise RuntimeError("No models available in Ollama")
    logger.info("Running inference on GPU with model: %s", model)
    start_time = time.time()
    constraints = job.get("constraints") or {}
    deterministic = constraints.get("deterministic_decoding", False)
    decode_seed = constraints.get("decode_seed") if deterministic else None
    ollama_client = AITBCHTTPClient(base_url="http://localhost:11434", timeout=_ollama_timeout_seconds())
    options: dict[str, Any] = {"num_predict": 24, "temperature": 0.7}
    if deterministic:
        options["temperature"] = 0
        options["top_k"] = 1
        options["top_p"] = 1
        options["seed"] = decode_seed if decode_seed is not None else 0
    ollama_payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options,
    }
    ollama_response = ollama_client.post("/api/generate", json=ollama_payload)
    if ollama_response:
        result = ollama_response
        output = result.get("response", "")
        execution_time = time.time() - start_time
        tee_quote = build_tee_quote(job, output=output)
        extra = {"model": model, "tokens_processed": result.get("eval_count", 0)}
        if tee_quote:
            logger.info("Attaching TEE quote for job %s", job_id)
        _submit_success(job_id, output, execution_time, extra, tee_quote=tee_quote)
        return True
    logger.error("Ollama error")
    _submit_failure(job_id, "Ollama error")
    return False


def _execute_circuit_model(job, circuit: ModelCircuit):
    """Run a registered ZK circuit model locally — no Ollama, no GPU (#2330).

    The requested model genuinely executes (the #1788 semantics are preserved:
    the result names the circuit that ran), the output is the deterministic
    field-array computation, and the coordinator-side receipt_model proof is
    generated by the coordinator itself.
    """
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    prompt = payload.get("prompt", "")
    logger.info("Running ZK circuit model %s for job %s", circuit.name, job_id)
    start_time = time.time()
    input_values = text_to_field_array(prompt, circuit.input_len)
    output_values = circuit.compute_output(input_values)
    output = json.dumps(output_values)
    execution_time = time.time() - start_time
    tee_quote = build_tee_quote(job, output=output)
    extra = {"model": circuit.name}
    if tee_quote:
        logger.info("Attaching TEE quote for job %s", job_id)
    _submit_success(job_id, output, execution_time, extra, tee_quote=tee_quote)
    return True


def _execute_transcribe(job):
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    url = payload.get("url") or payload.get("input")
    if not url:
        raise RuntimeError("Transcribe job requires 'url' or 'input' in payload")
    filename = payload.get("filename", "")
    model = payload.get("model", "base")
    logger.info("Running transcription with model: %s", model)
    start_time = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        source = filename or url.split("?")[0]
        ext = _safe_name(os.path.splitext(source)[1], "bin")
        input_path = os.path.join(tmp, f"input.{ext}")
        _download_media(url, input_path)
        constraints = job.get("constraints") or {}
        text = _run_whisper(
            input_path,
            model,
            deterministic=constraints.get("deterministic_decoding", False),
            seed=constraints.get("decode_seed"),
            access_headers=_shop_access_headers(payload, job_id),
        )
    execution_time = time.time() - start_time
    tee_quote = build_tee_quote(job, output=text)
    if tee_quote:
        logger.info("Attaching TEE quote for job %s", job_id)
    _submit_success(job_id, text, execution_time, {"model": model, "transcription": text}, tee_quote=tee_quote)
    return True


def _execute_reencode(job):
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    url = payload.get("url") or payload.get("input")
    if not url:
        raise RuntimeError("Re-encode job requires 'url' or 'input' in payload")
    filename = payload.get("filename", "")
    output_format = payload.get("output_format") or payload.get("format") or "mp4"
    logger.info("Running re-encode to format: %s", output_format)
    start_time = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        source = filename or url.split("?")[0]
        input_ext = _safe_name(os.path.splitext(source)[1], "bin")
        input_path = os.path.join(tmp, f"input.{input_ext}")
        _download_media(url, input_path)
        # output_format lands in the output filename AND ffmpeg's -f argument;
        # a buyer-controlled value with separators would escape tmp (#1483).
        output_format = _require_safe_name(payload.get("output_format") or payload.get("format") or "mp4", "output_format")
        output_path = os.path.join(tmp, f"output.{output_format}")
        summary = _run_ffmpeg(input_path, output_path, output_format)
    execution_time = time.time() - start_time
    tee_quote = build_tee_quote(job, output=summary.get("stderr", ""))
    if tee_quote:
        logger.info("Attaching TEE quote for job %s", job_id)
    _submit_success(job_id, summary["stderr"], execution_time, summary, tee_quote=tee_quote)
    return True


# A rental holds one worker thread for its whole duration and a thread cannot be
# killed, so the buyer's duration is clamped to a ceiling the node sets.
_GPU_COMPUTE_MAX_ENV = "GPU_COMPUTE_MAX_SECONDS"
_GPU_COMPUTE_DEFAULT_MAX_SECONDS = 3600
_GPU_COMPUTE_DEFAULT_SECONDS = 60


def _gpu_compute_max_seconds() -> int:
    try:
        return max(1, int(os.environ.get(_GPU_COMPUTE_MAX_ENV, _GPU_COMPUTE_DEFAULT_MAX_SECONDS)))
    except ValueError:
        return _GPU_COMPUTE_DEFAULT_MAX_SECONDS


def _duration_number(name, value):
    """A payload duration as a number, or TypeError/ValueError (the job then fails)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if value < 0 or (isinstance(value, float) and not math.isfinite(value)):
        raise ValueError(f"{name} must be a finite, non-negative number, got {value!r}")
    return value


def _gpu_compute_requested_seconds(payload):
    """The validated duration the buyer asked for; the default when it asked for none."""
    seconds = payload.get("duration_seconds")
    if not seconds:
        seconds = _duration_number("duration_hours", payload.get("duration_hours") or 0) * 3600
    else:
        seconds = _duration_number("duration_seconds", seconds)
    return seconds or _GPU_COMPUTE_DEFAULT_SECONDS


def _job_deadline(job):
    """The job's expires_at as epoch seconds (a number or an ISO-8601 string), else None."""
    return _epoch_seconds(job.get("expires_at"))


def _epoch_seconds(raw):
    """A timestamp as epoch seconds: number or ISO-8601 string, else None."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if math.isfinite(raw) else None
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Ignoring unparsable timestamp %r", raw)
            return None
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()
    return None


def _gpu_compute_rental_window(job):
    """#2317: the coordinator's rental-window fields, or None when absent.

    ``AssignedJob.gpu_compute`` carries ``started_at`` (RUNNING entry),
    ``duration_seconds`` (purchased) and ``rental_deadline`` (hard cutoff,
    epoch seconds). Older coordinators omit the block entirely — callers then
    keep the previous full-duration/expires_at behaviour.
    """
    info = job.get("gpu_compute")
    if not isinstance(info, dict):
        return None
    started = _epoch_seconds(info.get("started_at"))
    deadline = _epoch_seconds(info.get("rental_deadline"))
    raw_duration = info.get("duration_seconds")
    try:
        purchased = float(raw_duration) if raw_duration is not None else None
    except (TypeError, ValueError):
        purchased = None
    if purchased is not None and not math.isfinite(purchased):
        purchased = None
    if started is None and deadline is None and purchased is None:
        return None
    return {"started_at": started, "duration_seconds": purchased, "rental_deadline": deadline}


def _execute_gpu_compute(job):
    """Run a fixed-duration GPU compute rental.

    The payload carries a duration; the worker holds the reservation for that
    time, snapshots the GPU at start and end, and returns a completion proof.
    This is enough for market rental settlement; heavier workloads can be
    layered on top later.

    The duration is validated (finite, non-negative), clamped to
    GPU_COMPUTE_MAX_SECONDS, and the hold ends early once the job's
    ``expires_at`` passes, so a payload cannot keep a worker past either bound.
    """
    job_id = job.get("job_id")
    payload = job.get("payload", {})
    task = payload.get("task", "general_compute")
    requested_seconds = _gpu_compute_requested_seconds(payload)
    duration_seconds = min(requested_seconds, _gpu_compute_max_seconds())
    # #2317: on a resumed rental (miner restart / reconcile re-dispatch) the
    # purchased window started at the job's RUNNING entry, not now — hold only
    # the remaining purchased seconds, and break at the coordinator's rental
    # deadline rather than expires_at when the dispatch shape carries it.
    window = _gpu_compute_rental_window(job)
    hold_seconds = duration_seconds
    if window is not None:
        started = window["started_at"]
        purchased = window["duration_seconds"]
        if started is not None and purchased is not None and purchased > 0:
            remaining = started + purchased - time.time()
            hold_seconds = min(max(remaining, 0.0), duration_seconds)
            if hold_seconds < duration_seconds:
                logger.info(
                    "Job %s resumes a gpu_compute rental: %ss of %ss purchased remain",
                    job_id,
                    hold_seconds,
                    purchased,
                )
    deadline = (window or {}).get("rental_deadline") or _job_deadline(job)
    if duration_seconds < requested_seconds:
        logger.warning(
            "Job %s asked for %ss of GPU compute; holding %ss (%s)",
            job_id,
            requested_seconds,
            duration_seconds,
            _GPU_COMPUTE_MAX_ENV,
        )

    logger.info("Running GPU compute rental for %ss (%s)", duration_seconds, task)
    start_time = time.time()
    start_snapshot = _gpu_snapshot()

    # Hold the reservation in small sleeps so we can still be interrupted.
    elapsed = 0
    while elapsed < hold_seconds:
        if deadline is not None and time.time() >= deadline:
            logger.warning("Job %s passed its deadline after %ss of %ss; ending the rental", job_id, elapsed, hold_seconds)
            break
        sleep_chunk = min(5, hold_seconds - elapsed)
        time.sleep(sleep_chunk)
        elapsed += sleep_chunk

    end_snapshot = _gpu_snapshot()
    execution_time = time.time() - start_time
    output = f"GPU rental completed: {task} for {elapsed}s"
    tee_quote = build_tee_quote(job, output=output)
    if tee_quote:
        logger.info("Attaching TEE quote for job %s", job_id)
    _submit_success(
        job_id,
        output,
        execution_time,
        {
            "task": task,
            "duration_seconds": elapsed,
            "requested_seconds": requested_seconds,
            "gpu_start": start_snapshot,
            "gpu_end": end_snapshot,
        },
        tee_quote=tee_quote,
    )
    return True
