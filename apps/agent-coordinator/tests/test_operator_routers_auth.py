"""Auth-wiring coverage for the operator routers (#1545 / TEST-AUDIT-1).

``users.py``, ``alerts.py``, ``monitoring.py`` and ``auth.py`` gate on
``Depends(get_current_user)`` + ``permission_manager`` checks +
``require_role`` — a different stack than the agent-envelope ``principal``
dependency pinned by ``test_sec8_route_auth.py``. A dropped dependency on
any of these routes (role assignment, alert resolve, API-key revoke) would
ship silently, so this file pins:

* anonymous callers → 401 on every protected route;
* an authenticated ``user``-role principal → 403 where a permission or
  role is required, 200 where the route is self-scoped or auth-only;
* an ``admin`` principal → 200 across the board;
* a route inventory that fails when a new route appears without a
  ``current_user`` dependency outside the explicit public allowlist
  (the ``/api/v1/auth/*`` login/refresh/validate surface and the
  Prometheus ``/metrics*`` scrapes, which are public by design).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitbc.auth import Role, permission_manager  # noqa: E402
from aitbc.auth.jwt import create_access_token  # noqa: E402

from agent_app.routers import alerts as alerts_router  # noqa: E402
from agent_app.routers import auth as auth_router  # noqa: E402
from agent_app.routers import monitoring as monitoring_router  # noqa: E402
from agent_app.routers import users as users_router  # noqa: E402

ADMIN_USER = "test-admin-1545"
USER_USER = "test-user-1545"


@pytest.fixture(autouse=True)
def _restore_permission_manager():
    """permission_manager is a process-global singleton; don't leak grants."""
    snapshot = (
        dict(permission_manager.user_roles),
        {k: set(v) for k, v in permission_manager.user_permissions.items()},
        {k: set(v) for k, v in permission_manager.custom_permissions.items()},
    )
    yield
    permission_manager.user_roles.clear()
    permission_manager.user_roles.update(snapshot[0])
    permission_manager.user_permissions.clear()
    permission_manager.user_permissions.update(snapshot[1])
    permission_manager.custom_permissions.clear()
    permission_manager.custom_permissions.update(snapshot[2])


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(users_router.router)
    app.include_router(alerts_router.router)
    app.include_router(monitoring_router.router)
    app.include_router(auth_router.router)
    return TestClient(app)


def _admin_headers() -> dict[str, str]:
    permission_manager.assign_role(ADMIN_USER, Role.ADMIN)
    token = create_access_token(user_id=ADMIN_USER, role=Role.ADMIN.value)
    return {"Authorization": f"Bearer {token}"}


def _user_headers() -> dict[str, str]:
    permission_manager.assign_role(USER_USER, Role.USER)
    token = create_access_token(user_id=USER_USER, role=Role.USER.value)
    return {"Authorization": f"Bearer {token}"}


# (method, url, kwargs) — every route carrying Depends(get_current_user).
# DELETE /api-key additionally needs the X-Api-Key header for the *target*
# key; a dummy value still reaches the handler (revoke of an unknown key
# returns an error dict, not an HTTP error).
PROTECTED_CALLS = [
    ("POST", "/users/victim/role?role=user", {}),
    ("GET", "/users/victim/role", {}),
    ("GET", "/users/victim/permissions", {}),
    ("POST", "/users/victim/permissions/grant?permission=user:view", {}),
    ("DELETE", "/users/victim/permissions/user:view", {}),
    ("GET", "/roles", {}),
    ("GET", "/roles/admin", {}),
    ("GET", "/auth/stats", {}),
    ("GET", "/protected/admin", {}),
    ("GET", "/protected/operator", {}),
    ("GET", "/alerts", {}),
    ("POST", "/alerts/alert-1/resolve", {}),
    ("GET", "/alerts/stats", {}),
    ("GET", "/alerts/rules", {}),
    ("GET", "/sla", {}),
    ("POST", "/sla/sla-1/record?value=1.5", {}),
    ("GET", "/system/health", {}),
    ("GET", "/system/status", {}),
    ("POST", "/api/v1/auth/api-key/generate?user_id=someone", {"json": ["agent:view"]}),
    ("DELETE", "/api/v1/auth/api-key", {"headers": {"X-Api-Key": "key-to-revoke"}}),
]

# Routes a Role.USER principal must NOT reach: they need a permission the
# USER role lacks (USER_VIEW / SECURITY_* / USER_MANAGE_ROLES) or an
# ADMIN/OPERATOR role.
USER_FORBIDDEN_CALLS = [
    ("POST", "/users/victim/role?role=user", {}),
    ("GET", "/users/victim/role", {}),
    ("GET", "/users/victim/permissions", {}),
    ("POST", "/users/victim/permissions/grant?permission=user:view", {}),
    ("DELETE", "/users/victim/permissions/user:view", {}),
    ("GET", "/roles", {}),
    ("GET", "/roles/admin", {}),
    ("GET", "/auth/stats", {}),
    ("GET", "/protected/admin", {}),
    ("GET", "/protected/operator", {}),
    ("GET", "/alerts", {}),
    ("POST", "/alerts/alert-1/resolve", {}),
    ("GET", "/alerts/stats", {}),
    ("GET", "/alerts/rules", {}),
    ("GET", "/sla", {}),
    ("POST", "/sla/sla-1/record?value=1.5", {}),
    ("POST", "/api/v1/auth/api-key/generate?user_id=someone", {"json": ["agent:view"]}),
    ("DELETE", "/api/v1/auth/api-key", {"headers": {"X-Api-Key": "key-to-revoke"}}),
]

# Routes a Role.USER principal MAY reach: self-scoped permission reads,
# the auth-only system status, and system health (USER holds
# SYSTEM_HEALTH).
USER_ALLOWED_CALLS = [
    ("GET", f"/users/{USER_USER}/permissions", {}),
    ("GET", "/system/status", {}),
    ("GET", "/system/health", {}),
]


def _call(client: TestClient, method: str, url: str, kwargs: dict, headers: dict | None = None):
    merged = {"headers": {**(kwargs.pop("headers", {}) if kwargs else {}), **(headers or {})}}
    return client.request(method, url, **merged, **kwargs)


class TestAnonymousRejected:
    @pytest.mark.parametrize("method,url,kwargs", PROTECTED_CALLS)
    def test_anonymous_401(self, client, method, url, kwargs):
        resp = _call(client, method, url, dict(kwargs))
        assert resp.status_code == 401, f"{method} {url}: {resp.status_code} {resp.text}"


class TestUserRoleGates:
    @pytest.mark.parametrize("method,url,kwargs", USER_FORBIDDEN_CALLS)
    def test_user_forbidden_403(self, client, method, url, kwargs):
        resp = _call(client, method, url, dict(kwargs), headers=_user_headers())
        assert resp.status_code == 403, f"{method} {url}: {resp.status_code} {resp.text}"

    @pytest.mark.parametrize("method,url,kwargs", USER_ALLOWED_CALLS)
    def test_user_allowed_200(self, client, method, url, kwargs):
        resp = _call(client, method, url, dict(kwargs), headers=_user_headers())
        assert resp.status_code == 200, f"{method} {url}: {resp.status_code} {resp.text}"


class TestAdminAllowed:
    @pytest.mark.parametrize("method,url,kwargs", PROTECTED_CALLS)
    def test_admin_ok(self, client, method, url, kwargs):
        resp = _call(client, method, url, dict(kwargs), headers=_admin_headers())
        assert resp.status_code == 200, f"{method} {url}: {resp.status_code} {resp.text}"


class TestRouteInventory:
    """Every route on these routers must carry a ``current_user``
    dependency unless it is on the public allowlist — this fails the
    commit when a new unguarded route appears."""

    PUBLIC_ROUTES = {
        auth_router: {
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/validate",
            "/api/v1/auth/api-key/validate",
        },
        monitoring_router: {"/metrics", "/metrics/summary", "/metrics/health"},
    }

    @pytest.mark.parametrize("mod", [users_router, alerts_router, monitoring_router, auth_router])
    def test_routes_have_auth_dependency(self, mod):
        import inspect

        public = self.PUBLIC_ROUTES.get(mod, set())
        missing = []
        for route in mod.router.routes:
            if route.path in public:
                continue
            params = inspect.signature(route.endpoint).parameters
            if "current_user" not in params:
                missing.append(f"{sorted(getattr(route, 'methods', set()) or set())} {route.path}")
        assert not missing, f"routes without get_current_user dependency: {missing}"
