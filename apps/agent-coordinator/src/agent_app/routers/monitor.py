"""Monitor router — intentionally unimplemented.

The mock endpoints that lived here were removed: behind a ``settings.debug``
gate they served a fabricated dashboard (``overall_status: operational``,
``uptime: 3600``, a fixed 2026-05-08 timestamp) and empty ``/miners``,
``/dashboard``, and ``/jobs`` lists. The router stays mounted so the
``ROUTERS`` import contract is stable, but it registers no routes — and the
four fabricated ``Monitor``-tagged paths are gone from the published
OpenAPI spec.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Monitor"])
