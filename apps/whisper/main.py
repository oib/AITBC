from typing import Annotated

"""
AITBC Whisper Transcription Service
Minimal FastAPI service wrapping faster-whisper for the software market.
Port: 8210
"""

import asyncio
import hashlib
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager

import uvicorn  # noqa: E402
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.health_checks import create_simple_health_response  # noqa: E402
from aitbc.media_guard import pyav_open_options  # noqa: E402
from aitbc.shop_gate import require_job_access  # noqa: E402

configure_logging(level="INFO", service_name="whisper", to_file=True)
logger = get_logger(__name__)

_model = None
_model_name = os.getenv("WHISPER_MODEL", "base")
_device = os.getenv("WHISPER_DEVICE", "cuda")
_compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "float16")

# Request limits. Transcription cost is a direct function of audio length --
# roughly 1G of transient allocation per ten minutes of it -- so these bound what
# a single caller can make the service allocate. They are deliberately coupled to
# the unit's MemoryMax: about 730M of the shipped 3G cap is the resident model,
# which leaves room for roughly fifteen minutes of audio before the MemoryHigh
# throttling band. Raise MemoryMax and these together, or neither.
_MAX_UPLOAD_BYTES = int(os.getenv("WHISPER_MAX_UPLOAD_MB", "100")) * 1024 * 1024
_MAX_AUDIO_SECONDS = float(os.getenv("WHISPER_MAX_AUDIO_MINUTES", "15")) * 60
# Matches the bound coordinator-api already declares on WhisperRequest.beam_size
# (ge=1, le=10). That contract existed; this service simply never enforced it.
_MAX_BEAM_SIZE = int(os.getenv("WHISPER_MAX_BEAM_SIZE", "10"))
# WHISPER-BLOCK-1 (#1422): faster-whisper's transcribe() is a synchronous
# CPU/GPU-bound call — running it on the event loop stalls /health and every
# other request for the whole decode, and unbounded concurrent jobs can each
# allocate ~1G of transient memory per 10 minutes of audio. Two near-cap jobs
# plus the ~730M resident model already exceed the unit's MemoryMax=3G, so the
# default admits exactly one transcription at a time; raise it only together
# with MemoryMax.
_MAX_CONCURRENT = int(os.getenv("WHISPER_MAX_CONCURRENT", "1"))
# Plain counter, not asyncio.Semaphore: the check-and-increment below has no
# await between it and the increment, so it is atomic on the event loop, and
# it survives loop restarts/test harnesses that a loop-bound primitive would
# not (#1422).
_inflight = 0
# faster-whisper language tags look like "en" or "zh"; anything else is a 400,
# not an unhandled decode error.
_LANGUAGE_RE = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,8})?$")
_UPLOAD_CHUNK = 1024 * 1024
# The whole request body, not just the file part: multipart adds boundaries and
# the other form fields on top, so the header check needs slack the per-file
# limit does not.
_MAX_BODY_BYTES = _MAX_UPLOAD_BYTES + _UPLOAD_CHUNK


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]

    logger.info(f"Loading Whisper model '{_model_name}' on {_device} ({_compute_type})...")
    _model = WhisperModel(_model_name, device=_device, compute_type=_compute_type)
    logger.info("Whisper model ready.")
    yield
    _model = None


app = FastAPI(title="AITBC Whisper Service", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def _reject_oversized_body(request: Request, call_next):
    """Refuse an oversized upload at the header, before any of it is spooled.

    The byte counter in _spool_upload bounds memory, but it runs too late to stop
    the transfer: resolving an UploadFile parameter means ``await request.form()``,
    and that consumes the entire multipart stream to disk before the endpoint is
    ever entered. A middleware is the only place that sees the request early
    enough to refuse it.

    Content-Length is absent on a chunked upload, and a caller can of course lie
    about it -- which is precisely why the streaming limit stays as the backstop
    rather than being replaced by this.
    """
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > _MAX_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Upload exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit"},
        )
    return await call_next(request)


@app.get("/health")
async def health():
    return create_simple_health_response(
        "whisper",
        status="ok",
        model=_model_name,
        device=_device,
        ready=_model is not None,
    )


@app.get("/models")
async def list_models():
    return {
        "models": [
            {"name": "tiny", "params": "39M", "vram_gb": 1},
            {"name": "base", "params": "74M", "vram_gb": 1},
            {"name": "small", "params": "244M", "vram_gb": 2},
            {"name": "medium", "params": "769M", "vram_gb": 5},
            {"name": "large", "params": "1550M", "vram_gb": 10},
            {"name": "turbo", "params": "809M", "vram_gb": 6},
        ],
        "loaded": _model_name,
    }


def _safe_suffix(filename: str | None) -> str:
    """Bound the caller-supplied extension before it becomes part of a filename.

    Not a traversal guard -- splitext() only returns text after the last dot of
    the last path segment, so the result can never contain a separator. This is
    about a multi-kilobyte "extension" turning into ENAMETOOLONG, and about the
    temp name staying something a human can recognise in a directory listing.
    """
    ext = os.path.splitext(filename or "")[1]
    if not ext or len(ext) > 10 or not ext[1:].isalnum():
        return ".wav"
    return ext.lower()


async def _spool_upload(file: UploadFile, suffix: str) -> str:
    """Stream the upload to disk, refusing to buffer more than the byte limit.

    This replaces ``tmp.write(await file.read())``, which put the entire upload in
    memory before anything had looked at it -- so peak RSS was a direct function
    of what the caller chose to send, with no ceiling anywhere in the path.
    """
    written = 0
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        while chunk := await file.read(_UPLOAD_CHUNK):
            written += len(chunk)
            if written > _MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
                )
            tmp.write(chunk)
        tmp.close()
    except BaseException:
        # delete=False means the file outlives its handle, and its name has not
        # been returned to anyone yet -- this is the only chance to remove it.
        tmp.close()
        os.unlink(tmp.name)
        raise
    return tmp.name


def _probe_duration(path: str) -> float | None:
    """Container duration read from the header, without decoding anything.

    ``av`` is faster-whisper's own decoder -- ``faster_whisper.audio.decode_audio``
    opens the file with it -- so this adds no dependency and asks the same parser
    that will later do the real work. Reading the header is the whole point:
    ``WhisperModel.transcribe()`` decodes the entire clip into memory before it
    reports ``info.duration``, far too late to refuse the job on those grounds.

    The open carries the CE-001 (#1170) input guard, so a playlist or script that
    FFmpeg would sniff out of an innocently named upload is refused here instead of
    being followed to nested resources. It raises for anything the guard or the
    parser rejects; callers decide what that means.

    Returns None when the container carries no duration, which is normal for
    streamed formats; the byte limit is what covers that case.
    """
    import av

    with av.open(path, options=pyav_open_options()) as container:
        if container.duration is None:
            return None
        return container.duration / av.time_base


def _audio_seconds(path: str) -> float | None:
    """``_probe_duration`` that answers None for something it cannot read."""
    try:
        return _probe_duration(path)
    except Exception:
        # Diagnosing the format is not this function's job; see _probe_duration.
        return None


def _transcribe_sync(path: str, language: str | None, task: str, beam_size: int) -> dict:
    """Run the blocking model call and drain the segment generator.

    Everything in here is synchronous and CPU/GPU-bound; callers must run it
    via ``asyncio.to_thread`` so the event loop stays responsive (#1422).
    """
    segments, info = _model.transcribe(
        path,
        beam_size=beam_size,
        language=language,
        task=task,
    )
    segment_list = []
    full_text = []
    for seg in segments:
        segment_list.append(
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            }
        )
        full_text.append(seg.text.strip())
    return {
        "segment_list": segment_list,
        "full_text": full_text,
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 2),
    }


@app.post("/transcribe", dependencies=[Depends(require_job_access)])
async def transcribe(
    file: Annotated[UploadFile, File(...)],
    language: str | None = Form(default=None),
    task: str = Form(default="transcribe"),
    beam_size: int = Form(default=5),
):
    """Transcribe audio file. Returns transcript, duration, language, and segments."""
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    if task not in ("transcribe", "translate"):
        raise HTTPException(status_code=400, detail="task must be 'transcribe' or 'translate'")
    if not 1 <= beam_size <= _MAX_BEAM_SIZE:
        raise HTTPException(status_code=400, detail=f"beam_size must be between 1 and {_MAX_BEAM_SIZE}")
    if language is not None and not _LANGUAGE_RE.fullmatch(language):
        raise HTTPException(status_code=400, detail="language must be a language tag like 'en'")

    # Refuse before spooling: a queued request would otherwise hold a temp
    # file (and eventually memory) for work it cannot start yet (#1422).
    global _inflight
    if _inflight >= _MAX_CONCURRENT:
        raise HTTPException(status_code=503, detail="Transcription service busy; retry later")
    _inflight += 1
    try:
        tmp_path = await _spool_upload(file, _safe_suffix(file.filename))
    except BaseException:
        _inflight -= 1
        raise

    try:
        try:
            seconds = _probe_duration(tmp_path)
        except Exception:
            # Unreadable, or not one of the plain audio/video containers media_guard
            # allows. faster-whisper would open the same file with no guard at all,
            # so it never gets to see it (CE-001, #1170).
            raise HTTPException(status_code=415, detail="Unsupported or unreadable media container") from None
        if seconds is not None and seconds > _MAX_AUDIO_SECONDS:
            raise HTTPException(
                status_code=413,
                detail=(f"Audio is {seconds / 60:.1f} minutes; the limit is {_MAX_AUDIO_SECONDS / 60:.0f} minutes"),
            )

        t_start = time.time()
        result = await asyncio.to_thread(_transcribe_sync, tmp_path, language, task, beam_size)
        elapsed = round(time.time() - t_start, 2)
        transcript = " ".join(result["full_text"])
        result_hash = hashlib.sha256(transcript.encode()).hexdigest()
        duration = result["duration"]

        return JSONResponse(
            {
                "text": transcript,
                "language": result["language"],
                "language_probability": result["language_probability"],
                "duration_seconds": duration,
                "duration_minutes": round(duration / 60, 4),
                "segments": result["segment_list"],
                "model": _model_name,
                "elapsed_seconds": elapsed,
                "real_time_factor": round(elapsed / duration, 3) if duration > 0 else 0,
                "result_hash": result_hash,
            }
        )
    finally:
        os.unlink(tmp_path)
        _inflight -= 1


if __name__ == "__main__":
    import os

    # Standardized environment variable naming: SERVICE_BIND_HOST and SERVICE_BIND_PORT
    # code default only; the effective bind is pinned per host in the systemd unit. the containers run no firewall of their own, so a bind-all default is reachable by every other container on the bridge; accepted deviation tracked in docs/deployment/NETWORK_POLICY.md, not a safe fallback
    host = os.getenv("WHISPER_BIND_HOST", "0.0.0.0")  # nosec B104
    port = int(os.getenv("WHISPER_BIND_PORT", os.getenv("WHISPER_PORT", "8110")))

    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
