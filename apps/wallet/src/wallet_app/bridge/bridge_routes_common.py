"""Shared APIRouter objects for the wallet bridge route modules (#1860).

Extracted from ``bridge_routes.py`` so the route-section siblings
(``bridge_routes_deposits``, ``bridge_routes_sell``, ``bridge_routes_admin``)
can decorate the same router objects without a circular import: every
consumer — ``bridge_routes`` itself and the siblings — imports the routers
from here, and ``bridge_router`` remains the single object tests include
into a FastAPI app.
"""

from fastapi import APIRouter

exchange_router = APIRouter(prefix="/v1/exchange", tags=["exchange"])
bridge_router = APIRouter(prefix="/v1/bridge", tags=["bridge"])
price_router = APIRouter(tags=["exchange"])
