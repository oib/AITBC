"""Entry point for the memory service."""

from fastapi import FastAPI

from aitbc.aitbc_logging import configure_logging, get_logger

from .api import router
from .config import settings

configure_logging(level=settings.log_level, service_name="memory", to_file=True)
logger = get_logger(__name__)

app = FastAPI(title=settings.service_name, version="0.11.0")
app.include_router(router, prefix=settings.api_prefix)


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
