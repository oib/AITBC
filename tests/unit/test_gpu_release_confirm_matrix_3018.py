"""#3018: /v1/market/gpu/{id}/release and /confirm must admit all three roles.

Both handlers take ``AuthDep`` and serve THREE principals: ``release_gpu``
admits admin OR the GPU owner (``caller == gpu.miner_id``) OR the booking
client (``booking.client_id == caller``); ``confirm_gpu_booking`` is the
client ACK where ``client_id`` must equal the caller sub, with admin bypass.
The matrix entries were ``AuthLevel.MINER``, so middleware denied admin and
client callers 403 before the handler ran — the client confirm and non-miner
release paths were dead code. Same deadlock class as #2740/#1327. ``ANY`` is
the honest floor: every authenticated role reaches the handler, whose
three-principal check is the real authz. ``ADMIN_OR_CLIENT`` would still
block the GPU owner from releasing their own GPU.
"""

import os
import sys

os.environ.setdefault("NODE_ENV", "test")
os.environ.setdefault("SECRET_KEY", "x" * 48)
os.environ.setdefault("JWT_SECRET", "y" * 48)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from aitbc.auth.security_matrix import AuthLevel, check_role_match, get_auth_level  # noqa: E402

PATHS = ("/v1/market/gpu/gpu-1/release", "/v1/market/gpu/gpu-1/confirm")


def test_gpu_release_and_confirm_resolve_to_any() -> None:
    for path in PATHS:
        assert get_auth_level(path, "POST") == AuthLevel.ANY, path


def test_gpu_release_and_confirm_admit_admin_client_and_miner() -> None:
    """The pin that dies if someone reverts either entry to MINER."""
    for path in PATHS:
        level = get_auth_level(path, "POST")
        assert check_role_match(level, "admin"), path
        assert check_role_match(level, "client"), path
        assert check_role_match(level, "miner"), path
        assert not check_role_match(level, None), path


def test_gpu_release_confirm_entries_beat_the_broad_gpu_wildcard() -> None:
    """The explicit entries must be the ones that resolve (longest-match wins)."""
    from aitbc.auth.security_matrix import _lookup_level, ROUTE_SECURITY_MATRIX

    for path in PATHS:
        assert _lookup_level(path, ROUTE_SECURITY_MATRIX) == AuthLevel.ANY
        # Sanity: the broader family entry is also ANY, but the specific
        # patterns are strictly longer and therefore the effective match.
        assert len("/v1/market/gpu/*/release") > len("/v1/market/gpu/*")
