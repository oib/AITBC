"""Monitor router — intentionally unimplemented.

The mock endpoints that lived here were removed: behind a ``settings.debug``
gate they served a fabricated dashboard (``overall_status: operational``,
``uptime: 3600``, a fixed 2026-05-08 timestamp) and empty ``/miners``,
``/dashboard/history``, and ``/jobs`` lists. The router stays mounted at
``/v1`` so the module/import contract is stable, but it registers no routes.

Real monitoring surfaces exist elsewhere: ``/health`` and the
``monitoring_dashboard`` router, plus per-service status endpoints. The
removed ``/jobs`` and ``/status`` paths also collided with real routes
(``/v1/jobs`` job listing, ``/v1/status`` blockchain status) whenever the
debug gate was open — one more reason they had to go.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Monitor"])
