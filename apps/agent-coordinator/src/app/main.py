import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .exceptions import register_exception_handlers
from .lifespan import lifespan
from .middleware import register_middleware
from .routers import ROUTERS


def create_app() -> FastAPI:
    app = FastAPI(
        title="AITBC Agent Coordinator",
        description="Advanced multi-agent coordination and management system",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in ROUTERS:
        app.include_router(router)

    register_middleware(app)
    register_exception_handlers(app)
    return app


app = create_app()


def main():
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
