from typing import Annotated

"""
AITBC FFmpeg Video Processing Service
FastAPI service wrapping FFmpeg with GPU acceleration (NVENC/NVDEC)
Port: 8230
"""

import asyncio
import hashlib
import os
import re
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager

import uvicorn  # noqa: E402
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402
from aitbc.health_checks import create_simple_health_response  # noqa: E402
from aitbc.media_guard import ffmpeg_input_guard  # noqa: E402
from aitbc.shop_gate import require_job_access  # noqa: E402
from aitbc.utils.env import subprocess_env  # noqa: E402

configure_logging(level="INFO", service_name="ffmpeg", to_file=True)
logger = get_logger(__name__)

_device = os.getenv("FFMPEG_GPU_DEVICE", "0")
_hw_accel = os.getenv("FFMPEG_HW_ACCEL", "cuda")

# Island IPFS daemon — the delivered output is uploaded here so the buyer can
# fetch it, then the local file is deleted (#799). Same env name the miner's
# task executor uses.
_ISLAND_IPFS_API = os.getenv("ISLAND_IPFS_API", "http://127.0.0.1:5002")

# Request limit. Per-request cost tracks upload size -- the transcode child and
# the output read-back for hashing both scale with it -- so this bounds what a
# single caller can make the service allocate. It is deliberately coupled to the
# unit's MemoryMax=2G: the measured 229M job peaked at 1.16G, so 512MB leaves
# headroom for the ffmpeg child and the hashed output without reaching the
# MemoryHigh throttling band. Raise MemoryMax and this together, or neither.
_MAX_UPLOAD_BYTES = int(os.getenv("FFMPEG_MAX_UPLOAD_MB", "512")) * 1024 * 1024
_UPLOAD_CHUNK = 1024 * 1024
# The whole request body, not just the file part: multipart adds boundaries and
# the other form fields on top, so the header check needs slack the per-file
# limit does not.
_MAX_BODY_BYTES = _MAX_UPLOAD_BYTES + _UPLOAD_CHUNK

# FFMPEG-ARGV-1 (#1456): caller-controlled form fields reach the ffmpeg argv.
# codec becomes the -c:v encoder name, bitrate becomes -b:v/-maxrate/-bufsize,
# so both are validated to the shapes the encoder map and ffmpeg actually
# understand before they are interpolated — anything else is a 400, never a
# decode-time ffmpeg error or an IndexError 500.
_CODEC_RE = re.compile(r"^[a-z0-9_]{1,16}$")
_BITRATE_RE = re.compile(r"^\d{1,4}(\.\d{1,3})?[kKmMgG]?$")
# ~400 Mbit/s ceiling: generous for any legitimate transcode, small enough
# that a nonsense rate cannot size absurd VBV buffers.
_MAX_BITRATE_BPS = 400_000_000
_BITRATE_UNITS = {"k": 1_000, "m": 1_000_000, "g": 1_000_000_000}

# FFMPEG-CONC-1 (#1459): each /process job spawns an ffmpeg child that may run
# for the full 3600s timeout against a shared GPU and the unit's MemoryMax=2G.
# Unbounded admission means N paid jobs fight for NVENC and RAM until the unit
# is OOM-killed or every job times out. The counter is a plain int — the
# check-and-increment has no await between it and the increment, so it is
# atomic on the event loop — default 2 concurrent transcodes.
_MAX_CONCURRENT = int(os.getenv("FFMPEG_MAX_CONCURRENT", "2"))
_inflight = 0

# FFMPEG-OUT-1 (#1648): output_format is caller-controlled and lands in the
# temp output's suffix, where ffmpeg picks the muxer from the extension. A
# segmenting muxer (m3u8/hls/dash) writes sidecar files the finally-cleanup
# never deletes, and nothing bounded the output's size — bitrate is capped
# but duration is not, so a long input yields an unbounded file in the
# unit's PrivateTmp. Allowlist non-segmenting containers, and pass -fs so an
# oversized transcode fails loudly instead of filling the disk. 4G default:
# generous for a legitimate 512MB-input transcode, small enough that two
# concurrent jobs cannot exhaust a normal node disk.
_OUTPUT_FORMATS = {"mp4", "mov", "mkv", "webm"}
_MAX_OUTPUT_BYTES = int(os.getenv("FFMPEG_MAX_OUTPUT_MB", "4096")) * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FFmpeg service"""
    # Verify FFmpeg with GPU support is available
    try:
        result = await _run_cmd(["ffmpeg", "-hwaccels"], timeout=15)
        if _hw_accel not in result.stdout:
            logger.warning(f"{_hw_accel} hardware acceleration not available in FFmpeg")
        else:
            logger.info(f"FFmpeg service ready with {_hw_accel} hardware acceleration")
    except Exception as e:
        logger.warning(f"FFmpeg not available: {e}")
    yield


app = FastAPI(title="AITBC FFmpeg Service", version="1.0.0", lifespan=lifespan)


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


async def _run_cmd(cmd: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Run a subprocess without blocking the event loop.

    Uses the asyncio subprocess API so a long-running job leaves the loop
    free to serve /health, and a timeout really kills the child instead of
    abandoning a worker thread (asyncio.to_thread cannot kill the process).
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=subprocess_env(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return subprocess.CompletedProcess(
        cmd,
        proc.returncode if proc.returncode is not None else 1,
        stdout.decode(errors="replace"),
        stderr.decode(errors="replace"),
    )


def _safe_suffix(filename: str | None) -> str:
    """Bound the caller-supplied extension before it becomes part of a filename.

    Not a traversal guard -- splitext() only returns text after the last dot of
    the last path segment, so the result can never contain a separator. This is
    about a multi-kilobyte "extension" turning into ENAMETOOLONG, and about the
    temp name staying something a human can recognise in a directory listing.
    """
    ext = os.path.splitext(filename or "")[1]
    if not ext or len(ext) > 10 or not ext[1:].isalnum():
        return ".mp4"
    return ext.lower()


def _ipfs_add_file(path: str, filename: str) -> str:
    """Upload a local file to the island IPFS daemon; returns the CID.

    Streams from disk — outputs can be as large as the 512 MB upload cap, so
    they must not be buffered whole (#799)."""
    import requests

    with open(path, "rb") as f:
        resp = requests.post(
            f"{_ISLAND_IPFS_API}/api/v0/add",
            files={"file": (filename, f)},
            timeout=600,
        )
    resp.raise_for_status()
    return str(resp.json().get("Hash"))


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


@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        result = await _run_cmd(["ffmpeg", "-version"], timeout=15)
        return create_simple_health_response(
            "ffmpeg",
            # The binary probe is the service's only real dependency; a
            # non-zero exit means every transcode would fail, so the status
            # must not stay "ok" just because the process is alive.
            status="ok" if result.returncode == 0 else "error",
            gpu_device=_device,
            hw_accel=_hw_accel,
            ready=result.returncode == 0,
        )
    except Exception as e:
        return create_simple_health_response(
            "ffmpeg",
            status="error",
            error=str(e),
            ready=False,
        )


@app.get("/capabilities")
async def capabilities():
    """List supported codecs, formats, and GPU info"""
    try:
        # Get GPU info
        gpu_info = {}
        try:
            result = await _run_cmd(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], timeout=15)
            if result.returncode == 0:
                gpu_info = {
                    "name": result.stdout.strip().split(",")[0],
                    "memory": result.stdout.strip().split(",")[1] if "," in result.stdout else "Unknown",
                }
        except Exception:
            pass

        # Get supported encoders
        encoders = []
        try:
            result = await _run_cmd(["ffmpeg", "-encoders"], timeout=10)
            if result.returncode == 0:
                # Parse encoders (focus on hardware encoders)
                for line in result.stdout.split("\n"):
                    if "h264" in line.lower() or "hevc" in line.lower():
                        encoders.append(line.strip())
        except Exception:
            pass

        return {
            "gpu": gpu_info,
            "hw_accel": _hw_accel,
            "supported_encoders": encoders[:20],  # Limit to first 20
            "gpu_device": _device,
        }
    except Exception as e:
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.post("/process", dependencies=[Depends(require_job_access)])
async def process_video(
    file: Annotated[UploadFile, File(...)],
    output_format: str = Form(default="mp4"),
    codec: str = Form(default="h264"),
    resolution: str = Form(default="1080p"),
    bitrate: str = Form(default="5M"),
):
    """Process video with GPU acceleration"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # FFMPEG-ARGV-1 (#1456): validate caller-controlled fields before they are
    # interpolated into the ffmpeg argv.
    codec_key = codec.strip().lower()
    if not _CODEC_RE.fullmatch(codec_key):
        raise HTTPException(status_code=400, detail="codec must be a short encoder label like 'h264' or 'hevc'")
    bitrate_value = bitrate.strip()
    if not _BITRATE_RE.fullmatch(bitrate_value):
        raise HTTPException(status_code=400, detail="bitrate must look like '5M', '2500k' or '10'")
    # Normalize to an explicit unit, then bound the rate itself.
    if not bitrate_value[-1].isalpha():
        bitrate_value = f"{bitrate_value}M"
    _num = float("".join(c for c in bitrate_value if c.isdigit() or c == "."))
    _unit = bitrate_value[-1].lower()
    if _num * _BITRATE_UNITS[_unit] > _MAX_BITRATE_BPS:
        raise HTTPException(status_code=400, detail=f"bitrate exceeds the {_MAX_BITRATE_BPS // 1_000_000}M cap")

    # FFMPEG-OUT-1 (#1648): the format picks the muxer via the temp suffix —
    # only non-segmenting containers are accepted. Empty means the default.
    output_format_key = (output_format or "").strip().lower() or "mp4"
    if output_format_key not in _OUTPUT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"output_format must be one of {sorted(_OUTPUT_FORMATS)}",
        )

    # Validate GPU acceleration is available
    try:
        result = await _run_cmd(["ffmpeg", "-hwaccels"], timeout=15)
        if _hw_accel not in result.stdout:
            logger.exception("Unhandled exception")

            raise HTTPException(status_code=503, detail="Internal server error")
    except Exception as e:
        logger.exception("Unhandled exception")

        raise HTTPException(status_code=503, detail="Internal server error") from e

    # FFMPEG-CONC-1 (#1459): admit at most _MAX_CONCURRENT transcodes. The
    # check-and-increment has no await between it and the increment, so it is
    # atomic on the event loop; the slot is released in the finally below.
    global _inflight
    if _inflight >= _MAX_CONCURRENT:
        raise HTTPException(status_code=503, detail="FFmpeg service busy; retry later")
    _inflight += 1

    # Create temporary files. The upload is spooled, never buffered whole --
    # see _spool_upload for why. Both suffixes go through _safe_suffix: the
    # caller controls output_format as much as the filename, and a "/" in
    # either lands in the temp path the kernel resolves.
    input_path: str | None = None
    output_path: str | None = None
    try:
        input_path = await _spool_upload(file, _safe_suffix(file.filename))
        output_suffix = _safe_suffix(f"out.{output_format_key}")
        with tempfile.NamedTemporaryFile(suffix=output_suffix, delete=False) as output_tmp:
            output_path = output_tmp.name
    except BaseException:
        # Setup failed after (or during) spooling — do not orphan the upload.
        if input_path is not None and os.path.exists(input_path):
            os.unlink(input_path)
        _inflight -= 1
        raise

    try:
        t_start = time.time()

        # Map requested codec to an FFmpeg encoder name.
        # `codec` from the CLI is a short label like "h264" or "hevc"; the actual
        # encoder depends on the accelerator (nvenc for NVIDIA cuda, vaapi for AMD/Intel, etc.).
        if _hw_accel == "cuda":
            encoder = f"{codec_key}_nvenc"
        elif _hw_accel == "vaapi":
            encoder = f"{codec_key}_vaapi"
        elif _hw_accel == "qsv":
            encoder = f"{codec_key}_qsv"
        elif codec_key == "h264":
            encoder = "libx264"
        elif codec_key == "hevc":
            encoder = "libx265"
        else:
            encoder = codec_key

        # bufsize mirrors the (already validated) bitrate value and unit.
        numeric = "".join(c for c in bitrate_value if c.isdigit() or c == ".")
        unit = bitrate_value[-1].lower()
        bufsize = f"{numeric}{unit}"

        # Build FFmpeg command. Hardware-accelerated decode + encode when possible.
        cmd = [
            "ffmpeg",
            "-hwaccel",
            _hw_accel,
            # CE-001 (#1170): the upload is untrusted and FFmpeg sniffs content, so a
            # playlist named .mp4 would otherwise fetch nested resources of its choosing.
            *ffmpeg_input_guard(),
            "-i",
            input_path,
            "-c:v",
            encoder,
            "-preset",
            "p6" if "_nvenc" in encoder else "medium",
            "-b:v",
            bitrate_value,
            "-maxrate",
            bitrate_value,
            "-bufsize",
            bufsize,
        ]

        # Add resolution scaling if specified
        if resolution == "1080p":
            cmd.extend(["-vf", "scale=1920:1080"])
        elif resolution == "720p":
            cmd.extend(["-vf", "scale=1280:720"])
        elif resolution == "480p":
            cmd.extend(["-vf", "scale=854:480"])

        # -fs bounds the output file itself (#1648): bitrate is capped but
        # duration is not, so without it a long input writes an unbounded
        # file into PrivateTmp. ffmpeg exits non-zero when the limit hits.
        cmd.extend(["-fs", str(_MAX_OUTPUT_BYTES), "-y", output_path])

        # Run FFmpeg
        process = await _run_cmd(cmd, timeout=3600)  # 1 hour timeout

        elapsed = round(time.time() - t_start, 2)

        if process.returncode != 0:
            logger.exception("Unhandled exception")

            raise HTTPException(status_code=500, detail="Internal server error")

        # Calculate result hash. The output can be as large as the input, so it
        # is read in chunks rather than buffered whole -- the upload guard only
        # helps if the read-back does not reintroduce the same unbounded buffer.
        digest = hashlib.sha256()
        with open(output_path, "rb") as f:
            for chunk in iter(lambda: f.read(_UPLOAD_CHUNK), b""):
                digest.update(chunk)
        file_hash = digest.hexdigest()

        # Get file size
        file_size = os.path.getsize(output_path)

        # Deliver via the island IPFS like the other exec handlers (#799,
        # ruling 1A): the caller gets the CID and the local file is deleted in
        # the finally below instead of leaking in the unit's tmpfs.
        try:
            # The IPFS filename gets the same sanitized extension the temp
            # output used — output_format is caller-controlled (#1456).
            output_cid = await asyncio.to_thread(_ipfs_add_file, output_path, f"output{output_suffix}")
        except Exception as e:
            logger.error("IPFS upload of ffmpeg output failed: %s", e)
            raise HTTPException(status_code=502, detail="output upload to IPFS failed") from e

        return JSONResponse(
            {
                "status": "completed",
                "output_cid": output_cid,
                "file_size_bytes": file_size,
                "processing_time_seconds": elapsed,
                "processing_time_hours": round(elapsed / 3600, 4),
                "codec": codec,
                "resolution": resolution,
                "bitrate": bitrate,
                "result_hash": file_hash,
                "gpu_device": _device,
                "hw_accel": _hw_accel,
            }
        )

    finally:
        # Cleanup input and output files — the output is delivered through
        # IPFS, keeping it local was the #799 tmpfs leak. The concurrency
        # slot is released here too (#1459).
        for _p in (input_path, output_path):
            if _p is not None and os.path.exists(_p):
                os.unlink(_p)
        _inflight -= 1


if __name__ == "__main__":
    import os

    # Standardized environment variable naming: SERVICE_BIND_HOST and SERVICE_BIND_PORT
    # code default only; the effective bind is pinned per host in the systemd unit. the containers run no firewall of their own, so a bind-all default is reachable by every other container on the bridge; accepted deviation tracked in docs/deployment/NETWORK_POLICY.md, not a safe fallback
    host = os.getenv("FFMPEG_BIND_HOST", "0.0.0.0")  # nosec B104
    port = int(os.getenv("FFMPEG_BIND_PORT", os.getenv("FFMPEG_PORT", "8230")))

    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
