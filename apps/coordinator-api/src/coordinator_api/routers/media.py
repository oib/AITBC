"""Media upload and download endpoints for AI job inputs.

v0.25.6: replaces the base64 ``data:`` URI fallback in ``aitbc ai submit`` with a
size-guarded coordinator upload. The CLI uploads local media files to
``/v1/media/upload`` and puts the returned download URL in the job payload;
miners download the file from ``/v1/media/download/{token}``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from ..auth import AdminOrClientDep
from ..config import settings


router = APIRouter(tags=["media"])


def _media_dir() -> Path:
    """Return (and create) the configured media storage directory."""
    path = Path(getattr(settings, "media_storage_dir", "/var/lib/aitbc/media"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _max_upload_bytes() -> int:
    """Return the configured per-file upload size limit in bytes."""
    return getattr(settings, "max_media_upload_bytes", 100 * 1024 * 1024)


@router.post("/media/upload", summary="Upload a media file", tags=["media"])
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

    # FastAPI/Starlette UploadFile does not expose size or full seek support;
    # stream to disk and enforce the limit as we write.
    token = uuid4().hex
    media_dir = _media_dir()
    storage_path = media_dir / token
    meta_path = media_dir / f"{token}.json"

    await file.seek(0)

    written = 0
    with storage_path.open("wb") as f:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            chunk_bytes = chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
            written += len(chunk_bytes)
            if written > max_bytes:
                f.close()
                storage_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"file exceeds limit of {max_bytes} bytes",
                )
            f.write(chunk_bytes)

    import json

    meta = {
        "filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": written,
    }
    meta_path.write_text(json.dumps(meta))

    download_url = str(request.url_for("download_media", token=token))
    return {
        "success": True,
        "token": token,
        "download_url": download_url,
        "filename": file.filename,
        "size": written,
        "content_type": meta["content_type"],
    }


@router.get("/media/download/{token}", summary="Download a media file", tags=["media"], name="download_media")
async def download_media(token: str) -> FileResponse:
    """Download a previously uploaded media file by token."""
    media_dir = _media_dir()
    storage_path = media_dir / token
    meta_path = media_dir / f"{token}.json"

    if not storage_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="media not found")

    filename = token
    content_type = "application/octet-stream"
    if meta_path.is_file():
        import json

        try:
            meta = json.loads(meta_path.read_text())
            filename = meta.get("filename", filename)
            content_type = meta.get("content_type", content_type)
        except Exception:
            pass

    return FileResponse(
        str(storage_path),
        media_type=content_type,
        filename=filename,
    )
