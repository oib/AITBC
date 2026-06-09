"""
Core module for Coordinator API.
"""

from .app import create_app
from .lifespan import lifespan
from .middleware import setup_middleware
from .routers import register_routers

__all__ = ['create_app', 'lifespan', 'setup_middleware', 'register_routers']
