"""#1809: importing ``aitbc_edge.main`` must not crash at route registration.

``readiness_check`` was annotated ``-> dict[str, str] | JSONResponse``. FastAPI
builds a response field from the return annotation whenever the decorator does
not pin ``response_model``, and ``dict | JSONResponse`` is not a valid Pydantic
field — ``add_api_route`` raised ``FastAPIError`` while the app object was being
assembled, so the service crash-looped at startup. Every router test builds its
own ``FastAPI()`` and ``include_router``s the routers directly, so no test ever
imported this module and the defect reached main (``8adfe09bf9``, #1540).

The import below IS the regression test: route registration happens at module
scope. ``response_model=None`` on the decorator is the established in-repo fix
(``trading_service/routers/system.py`` ``/ready`` uses the identical signature).
"""

from __future__ import annotations


def test_real_app_module_imports_and_registers_ready_route() -> None:
    import aitbc_edge.main as edge_main

    paths = {route.path for route in edge_main.app.routes}
    assert "/ready" in paths
    assert "/health" in paths
