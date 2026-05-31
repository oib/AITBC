"""FastAPI application wiring for the AITBC Pool Hub."""

from .main import app, create_app

__all__ = ["create_app", "app"]
