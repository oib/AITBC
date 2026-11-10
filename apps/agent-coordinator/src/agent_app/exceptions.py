from datetime import UTC, datetime
from typing import Any

from fastapi.responses import JSONResponse

from aitbc.aitbc_logging import get_logger
from aitbc.middleware import register_request_validation_error_handler

logger = get_logger(__name__)

__all__ = ["register_exception_handlers"]


def register_exception_handlers(app: Any) -> None:
    # #1676: literal NaN/Infinity JSON bodies must answer a serializable 422,
    # not a 500 — same handler the other money-path services install.
    register_request_validation_error_handler(app)

    @app.exception_handler(404)
    def not_found_handler(request: Any, exc: Any) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Resource not found", "timestamp": datetime.now(UTC).isoformat()},
        )

    @app.exception_handler(500)
    def internal_error_handler(request: Any, exc: Any) -> JSONResponse:
        logger.error("Internal server error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Internal server error", "timestamp": datetime.now(UTC).isoformat()},
        )
