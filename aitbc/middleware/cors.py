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
    allow_credentials: bool = False,
    allow_methods: list[str] | None = None,
    allow_headers: list[str] | None = None,
) -> None:
    """Add CORSMiddleware to a FastAPI app with sensible defaults.

    Args:
        app: FastAPI application instance.
        allow_origins: List of allowed origins. Defaults to ``["*"]`` (all origins).
        allow_credentials: Whether to allow credentials. Defaults to False to avoid
            the wildcard-with-credentials conflict.
        allow_methods: List of allowed HTTP methods. Defaults to all standard methods.
        allow_headers: List of allowed headers. Defaults to all headers.

    Raises:
        ValueError: If ``allow_origins`` contains ``"*"`` while ``allow_credentials``
            is enabled, which is a security risk in browsers.
    """
    if allow_origins is None:
        allow_origins = ["*"]
    if allow_methods is None:
        allow_methods = ["*"]
    if allow_headers is None:
        allow_headers = ["*"]

    if allow_credentials and "*" in allow_origins:
        raise ValueError("Wildcard CORS origins cannot be used with credentials enabled")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )
