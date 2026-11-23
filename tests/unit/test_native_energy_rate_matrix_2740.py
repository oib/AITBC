"""#2740: /v1/market/native-energy/rate must admit admin JWTs in middleware.

#2704 made ``POST /v1/market/native-energy/rate`` admin-only (``AdminDep``)
but left the path-level ``ROUTE_SECURITY_MATRIX`` entry at ``AuthLevel.MINER``.
The middleware runs before the handler, so every admin token was denied 403
"Forbidden" and the rate-refresh timer could never publish — the stored AIT/EUR
rate froze at version 67. The matrix is path-level only (GET shares the path),
so the honest floor is ``ANY``: any authenticated role reaches the route and
``AdminDep`` still rejects non-admin writes.
"""

import os
import sys

os.environ.setdefault("NODE_ENV", "test")
os.environ.setdefault("SECRET_KEY", "x" * 48)
os.environ.setdefault("JWT_SECRET", "y" * 48)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level  # noqa: E402

RATE_PATH = "/v1/market/native-energy/rate"


def test_rate_path_matrix_level_is_any() -> None:
    assert get_auth_level(RATE_PATH, "POST") == AuthLevel.ANY
    assert get_auth_level(RATE_PATH, "GET") == AuthLevel.ANY


def test_rate_path_admits_admin_and_miner_but_not_anonymous() -> None:
    level = get_auth_level(RATE_PATH, "POST")
    assert check_role_match(level, "admin")
    assert check_role_match(level, "miner")
    assert check_role_match(level, "client")
    assert not check_role_match(level, None)
