"""FastAPI application wiring for the AITBC Pool Hub."""

from .main import create_app, app

__all__ = ["create_app", "app"]
