"""#1856: scoped API-key permissions must bound permission_manager routes.

``get_current_user`` resolves an ``ApiKey`` credential to a principal whose
``user_id`` is the key's bound user and whose ``permissions`` are the key's
declared scope — but every ``permission_manager.has_permission(user_id, …)``
check read only the *user's* role store, so a key minted for ``admin_001``
passed every check regardless of its stated scope. These tests pin:

* ``principal_has_permission`` = role-store grant AND (for api_key
  principals) key-scope membership — intersection, fail-closed;
* a scoped key bound to a privileged user with an empty/mismatched scope
  gets 403 on a permission-gated route (pre-fix: 200);
* a key whose scope names the permission still passes when the bound user
  holds it;
* JWT principals are unaffected.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitbc.auth import Permission, Role, api_key_manager, permission_manager, principal_has_permission  # noqa: E402
from aitbc.auth.jwt import create_access_token  # noqa: E402

from agent_app.routers import alerts as alerts_router  # noqa: E402
from agent_app.routers import auth as auth_router  # noqa: E402

BOUND_ADMIN = "apikey-bound-admin-1856"


@pytest.fixture(autouse=True)
def _restore_permission_manager():
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
    app.include_router(alerts_router.router)
    app.include_router(auth_router.router)
    return TestClient(app)


def _mint_key(user_id: str, permissions: list[str]) -> str:
    result = api_key_manager.generate_api_key(user_id, permissions)
    assert result["status"] == "success"
    return result["api_key"]


class TestPrincipalHasPermission:
    def test_jwt_principal_uses_role_store(self):
        permission_manager.assign_role(BOUND_ADMIN, Role.ADMIN)
        user = {"user_id": BOUND_ADMIN, "auth_type": "jwt"}
        assert principal_has_permission(user, Permission.SECURITY_VIEW) is True

    def test_api_key_empty_scope_denied_despite_store_grant(self):
        permission_manager.assign_role(BOUND_ADMIN, Role.ADMIN)
        user = {"user_id": BOUND_ADMIN, "auth_type": "api_key", "permissions": []}
        assert principal_has_permission(user, Permission.SECURITY_VIEW) is False

    def test_api_key_scope_membership_required(self):
        permission_manager.assign_role(BOUND_ADMIN, Role.ADMIN)
        user = {"user_id": BOUND_ADMIN, "auth_type": "api_key", "permissions": ["security:view"]}
        assert principal_has_permission(user, Permission.SECURITY_VIEW) is True
        assert principal_has_permission(user, Permission.SECURITY_MANAGE) is False

    def test_api_key_scope_without_store_grant_denied(self):
        # Intersection: scope alone does not grant — the bound user must hold
        # the permission in the role store too.
        user = {"user_id": "never-logged-in", "auth_type": "api_key", "permissions": ["security:manage"]}
        assert principal_has_permission(user, Permission.SECURITY_MANAGE) is False


class TestScopedKeyOnGatedRoutes:
    def test_empty_scope_key_gets_403_on_alerts(self, client: TestClient):
        permission_manager.assign_role(BOUND_ADMIN, Role.ADMIN)
        key = _mint_key(BOUND_ADMIN, [])
        resp = client.get("/alerts", headers={"Authorization": f"ApiKey {key}"})
        assert resp.status_code == 403

    def test_scoped_key_with_permission_reaches_route(self, client: TestClient):
        permission_manager.assign_role(BOUND_ADMIN, Role.ADMIN)
        key = _mint_key(BOUND_ADMIN, ["security:view"])
        resp = client.get("/alerts", headers={"Authorization": f"ApiKey {key}"})
        assert resp.status_code == 200

    def test_scoped_key_cannot_generate_keys_without_scope(self, client: TestClient):
        permission_manager.assign_role(BOUND_ADMIN, Role.ADMIN)
        key = _mint_key(BOUND_ADMIN, ["security:view"])
        resp = client.post(
            "/api/v1/auth/api-key/generate?user_id=someone",
            json=["security:manage"],
            headers={"Authorization": f"ApiKey {key}"},
        )
        assert resp.status_code == 403

    def test_jwt_admin_unaffected(self, client: TestClient):
        permission_manager.assign_role(BOUND_ADMIN, Role.ADMIN)
        token = create_access_token(user_id=BOUND_ADMIN, role=Role.ADMIN.value)
        resp = client.get("/alerts", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
