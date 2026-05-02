from datetime import datetime, timezone

from aitbc import get_logger
from fastapi.responses import JSONResponse

logger = get_logger(__name__)


def register_exception_handlers(app):
    @app.exception_handler(404)
    async def not_found_handler(request, exc):
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "message": "Resource not found",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.exception_handler(500)
    async def internal_error_handler(request, exc):
        logger.error(f"Internal server error: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Internal server error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
