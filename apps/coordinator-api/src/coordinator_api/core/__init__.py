"""
Core module for Coordinator API.
"""

from .app import create_app
from .lifecycle import get_lifecycle_state, get_task_manager
from .lifespan import lifespan
from .middleware import setup_middleware
from .routers import register_routers

__all__ = ["create_app", "lifespan", "setup_middleware", "register_routers", "get_lifecycle_state", "get_task_manager"]
