"""CORS setup helper for AITBC services (v0.10.7 §B7).

Provides ``setup_cors()`` to standardize CORS middleware configuration
across all services, eliminating copy-pasted CORSMiddleware setup blocks.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def setup_cors(
    app: FastAPI,
    allow_origins: list[str] | None = None,
    allow_credentials: bool = True,
    allow_methods: list[str] | None = None,
    allow_headers: list[str] | None = None,
) -> None:
    """Add CORSMiddleware to a FastAPI app with sensible defaults.

    Args:
        app: FastAPI application instance.
        allow_origins: List of allowed origins. Defaults to ``["*"]`` (all origins).
        allow_credentials: Whether to allow credentials. Defaults to True.
        allow_methods: List of allowed HTTP methods. Defaults to all standard methods.
        allow_headers: List of allowed headers. Defaults to all headers.
    """
    if allow_origins is None:
        allow_origins = ["*"]
    if allow_methods is None:
        allow_methods = ["*"]
    if allow_headers is None:
        allow_headers = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )
