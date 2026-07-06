"""
Route security matrix — defines auth requirements for all routes.

.. deprecated::
    This module is a backward-compatibility shim. The canonical implementation
    lives in ``aitbc.auth.security_matrix``. Import from ``aitbc.auth``
    directly in new code.
"""

import warnings

from aitbc.auth.security_matrix import (
    AuthLevel,
    ROUTE_SECURITY_MATRIX,
    check_role_match,
    get_auth_level,
)

warnings.warn(
    "app.auth.security_matrix is deprecated; import from aitbc.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["AuthLevel", "ROUTE_SECURITY_MATRIX", "check_role_match", "get_auth_level"]
