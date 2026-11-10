"""Entry point for the memory service."""

from fastapi import FastAPI

from aitbc.middleware import RequestValidationMiddleware
from aitbc.aitbc_logging import configure_logging, get_logger

from .api import router
from .config import settings

configure_logging(level=settings.log_level, service_name="memory", to_file=True)
logger = get_logger(__name__)

app = FastAPI(title=settings.service_name, version="0.11.0")
app.include_router(router, prefix=settings.api_prefix)

# MEMORY-BODY-1 (#1652): the per-blob caps in config bound ``data``, but the
# route's encoded-length check runs only after FastAPI has read and parsed
# the whole request body — an unbounded JSON envelope (huge ``tags``, or a
# chunked body with no Content-Length) is a heap-exhaustion path the blob
# caps do not cover. The shared middleware enforces the cap on the bytes
# actually read and answers 413. Sized to the largest legal store payload
# (base64 inflates ~4/3) plus slack for the owner/tags envelope.
_MAX_REQUEST_BYTES = (settings.memory_max_blob_bytes * 4) // 3 + 1024 * 1024
app.add_middleware(RequestValidationMiddleware, max_request_size=_MAX_REQUEST_BYTES)


@app.on_event("startup")
async def startup() -> None:
    """Log service start."""
    logger.info("%s starting on %s:%s", settings.service_name, settings.app_host, settings.app_port)


@app.on_event("shutdown")
async def shutdown() -> None:
    """Log service shutdown."""
    logger.info("%s shutting down", settings.service_name)


def main() -> None:
    """Run the memory service with uvicorn."""
    import uvicorn

    uvicorn.run("memory_app.main:app", host=settings.app_host, port=settings.app_port, log_level="critical", access_log=False)


if __name__ == "__main__":
    main()
