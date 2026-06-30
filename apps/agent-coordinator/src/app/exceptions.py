from datetime import UTC, datetime
from typing import Any

from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: Any) -> None:
    @app.exception_handler(404)
    async def not_found_handler(request: Any, exc: Any) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Resource not found", "timestamp": datetime.now(UTC).isoformat()},
        )

    @app.exception_handler(500)
    async def internal_error_handler(request: Any, exc: Any) -> JSONResponse:
        logger.error("Internal server error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Internal server error", "timestamp": datetime.now(UTC).isoformat()},
        )
