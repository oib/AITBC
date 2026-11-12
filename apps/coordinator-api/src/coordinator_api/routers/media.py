"""Media upload and download endpoints for AI job inputs.

v0.25.6: replaces the base64 ``data:`` URI fallback in ``aitbc ai submit`` with a
size-guarded coordinator upload. The CLI uploads local media files to
``/v1/media/upload`` and puts the returned download URL in the job payload;
miners download the file from ``/v1/media/download/{token}``.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from ..auth import AdminOrClientDep
from ..config import settings
from aitbc.aitbc_logging import get_logger
from aitbc.rate_limiting import rate_limit

logger = get_logger(__name__)

# Expected failure surface for the best-effort meta sidecar read below:
# filesystem errors and data-shape errors from json.loads/attribute access
# on a corrupt or non-object sidecar. Genuine BaseExceptions still
# propagate (#1862).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
)

router = APIRouter(tags=["media"])


def _media_dir() -> Path:
    """Return (and create) the configured media storage directory."""
    path = Path(getattr(settings, "media_storage_dir", "/var/lib/aitbc/media"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _max_upload_bytes() -> int:
    """Return the configured per-file upload size limit in bytes."""
    return getattr(settings, "max_media_upload_bytes", 100 * 1024 * 1024)


def _media_quota() -> tuple[int, int, float]:
    """Return ``(max_total_bytes, max_files, ttl_seconds)`` for the media store."""
    return (
        int(getattr(settings, "media_storage_max_bytes", 10 * 1024**3)),
        int(getattr(settings, "media_storage_max_files", 10_000)),
        float(getattr(settings, "media_storage_ttl_seconds", 30 * 24 * 3600)),
    )


def _media_usage(media_dir: Path) -> tuple[list[tuple[float, int, Path]], int]:
    """Return ``([(mtime, size, path)], total_bytes)`` for stored blobs."""
    files: list[tuple[float, int, Path]] = []
    total = 0
    if not media_dir.is_dir():
        return files, total
    for path in media_dir.iterdir():
        # ``.json`` sidecars are metadata, not blobs.
        if path.name.endswith(".json") or not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        files.append((st.st_mtime, st.st_size, path))
        total += st.st_size
    return files, total


def _delete_blob_pair(media_dir: Path, blob: Path) -> int:
    """Delete a blob and its ``.json`` meta sidecar; return bytes freed."""
    freed = 0
    try:
        freed = blob.stat().st_size
    except OSError:
        pass
    blob.unlink(missing_ok=True)
    (media_dir / f"{blob.name}.json").unlink(missing_ok=True)
    return freed


def sweep_media_storage(
    media_dir: Path,
    *,
    max_bytes: int,
    max_files: int,
    ttl_seconds: float,
    now: float | None = None,
) -> dict[str, int]:
    """GC expired blobs and enforce the storage caps (#1752).

    Deletes blob+meta pairs older than ``ttl_seconds`` first, then evicts the
    oldest blobs until both the byte and file caps hold. Synchronous — callers
    on the event loop must run it via ``asyncio.to_thread``. Returns post-sweep
    ``{"bytes": ..., "files": ...}`` usage.
    """
    now = time.time() if now is None else now
    files, total = _media_usage(media_dir)

    # TTL pass.
    expired = [entry for entry in files if now - entry[0] > ttl_seconds]
    for _mtime, size, path in expired:
        _delete_blob_pair(media_dir, path)
        total -= size
    if expired:
        expired_names = {p.name for _m, _s, p in expired}
        files = [entry for entry in files if entry[2].name not in expired_names]

    # Cap pass: evict oldest until both limits hold.
    files.sort(key=lambda entry: entry[0])
    while files and (total > max_bytes or len(files) > max_files):
        _mtime, size, path = files.pop(0)
        _delete_blob_pair(media_dir, path)
        total -= size

    return {"bytes": total, "files": len(files)}


# Content types safe to serve inline on download. Everything else is
# normalized to application/octet-stream — the uploader's declared type is
# never reflected verbatim (#1752 stored-content/phishing surface).
# ``image/svg+xml`` is excluded explicitly: it is scriptable active content
# despite the ``image/`` prefix.
_SAFE_INLINE_PREFIXES = ("image/", "audio/", "video/")
_SAFE_INLINE_TYPES = {"text/plain", "application/json", "application/octet-stream"}
_UNSAFE_INLINE_TYPES = {"image/svg+xml"}


def _safe_media_type(content_type: str) -> str:
    """Return a safe download media type for a stored ``content_type``."""
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct in _UNSAFE_INLINE_TYPES:
        return "application/octet-stream"
    if ct in _SAFE_INLINE_TYPES or any(ct.startswith(prefix) for prefix in _SAFE_INLINE_PREFIXES):
        return ct
    return "application/octet-stream"


@router.post("/media/upload", summary="Upload a media file", tags=["media"])
@rate_limit(rate=20, per=60)
async def upload_media(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    user: AdminOrClientDep,
) -> dict[str, Any]:
    """Upload a media file for use as an AI job input.

    The caller receives an opaque token and a download URL. The download URL
    is valid for anyone who knows the token; keep the token as private as the
    job itself.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="filename is required")

    max_bytes = _max_upload_bytes()
    max_total_bytes, max_files, ttl_seconds = _media_quota()

    token = uuid4().hex
    media_dir = _media_dir()
    storage_path = media_dir / token
    meta_path = media_dir / f"{token}.json"

    # #1752: GC expired blobs and measure remaining quota before writing —
    # uploads are the only writer, so sweeping here bounds the directory.
    usage = await asyncio.to_thread(
        sweep_media_storage, media_dir, max_bytes=max_total_bytes, max_files=max_files, ttl_seconds=ttl_seconds
    )
    remaining_bytes = max_total_bytes - usage["bytes"]
    if remaining_bytes <= 0:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="media storage quota exceeded",
        )
    if usage["files"] >= max_files:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="media storage file-count quota exceeded",
        )
    # The effective per-file cap is the stricter of the per-upload limit and
    # the remaining global quota.
    effective_max = min(max_bytes, remaining_bytes)

    await file.seek(0)

    written = 0
    quota_exceeded = False
    with storage_path.open("wb") as f:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            chunk_bytes = chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
            written += len(chunk_bytes)
            if written > effective_max:
                f.close()  # noqa: unawaited-async — sync file handle
                storage_path.unlink(missing_ok=True)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"file exceeds limit of {max_bytes} bytes",
                    )
                quota_exceeded = True
                break
            f.write(chunk_bytes)
    if quota_exceeded:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="media storage quota exceeded",
        )

    meta = {
        "filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": written,
    }
    # #1752: the meta write is blocking filesystem IO — keep it off the loop.
    await asyncio.to_thread(meta_path.write_text, json.dumps(meta))

    # Build a public download URL that respects any reverse-proxy path prefix
    # (e.g. /c on the hub node) so workers receive an externally routable URL.
    prefix = request.headers.get("x-forwarded-prefix", "")
    if prefix:
        prefix = "/" + prefix.strip("/")
    base = str(request.base_url).rstrip("/")
    download_url = f"{base}{prefix}/v1/media/download/{token}"
    return {
        "success": True,
        "token": token,
        "download_url": download_url,
        "filename": file.filename,
        "size": written,
        "content_type": meta["content_type"],
    }


# #1932 F3: download tokens are uuid4().hex — anything else ("<hex>.json"
# sidecar names, traversal segments, arbitrary paths) is not a blob token.
_MEDIA_TOKEN_RE = re.compile(r"[0-9a-f]{32}")


@router.get("/media/download/{token}", summary="Download a media file", tags=["media"], name="download_media")
def download_media(token: str) -> FileResponse:
    """Download a previously uploaded media file by token."""
    if not _MEDIA_TOKEN_RE.fullmatch(token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="media not found")
    media_dir = _media_dir()
    storage_path = media_dir / token
    meta_path = media_dir / f"{token}.json"

    if not storage_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="media not found")

    filename = token
    content_type = "application/octet-stream"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text())
            filename = meta.get("filename", filename)
            content_type = meta.get("content_type", content_type)
        except _OPS_ERRORS:
            logger.debug("Ignoring unreadable media meta sidecar %s", meta_path, exc_info=True)

    # #1752: never reflect the uploader-declared type verbatim — active
    # content (text/html, image/svg+xml, ...) is normalized to
    # application/octet-stream. FileResponse already sends
    # Content-Disposition: attachment for every download.
    return FileResponse(
        str(storage_path),
        media_type=_safe_media_type(str(content_type)),
        filename=filename,
    )
