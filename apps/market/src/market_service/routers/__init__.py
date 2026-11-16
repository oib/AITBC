"""APIRouter modules for the market service.

Each module holds one cohesive group of routes verbatim from the former
monolithic ``main.py``; ``main`` includes the routers at app assembly.
Route paths, methods, decorators, and handler bodies are unchanged — only
the registration target moved from ``app`` to an ``APIRouter``.
"""
