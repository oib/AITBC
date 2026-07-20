"""Developer Platform API router.

This module aggregates the per-domain feature routers under the
``/developer-platform`` prefix. It is kept as the public export for
backwards compatibility with existing imports.
"""

from fastapi import APIRouter

from .analytics import router as analytics_router
from .bounties import router as bounties_router
from .certifications import router as certifications_router
from .developers import router as developers_router
from .hubs import router as hubs_router
from .staking import router as staking_router

router = APIRouter(prefix="/developer-platform", tags=["Developer Platform"])

router.include_router(developers_router)
router.include_router(bounties_router)
router.include_router(certifications_router)
router.include_router(hubs_router)
router.include_router(staking_router)
router.include_router(analytics_router)
