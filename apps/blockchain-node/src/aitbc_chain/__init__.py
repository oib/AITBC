"""AITBC blockchain node package."""
from typing import Any

# Lazy import to avoid cascading dependencies
def create_app() -> Any:
    from .app import create_app as _create_app
    return _create_app()

__all__ = ["create_app"]
