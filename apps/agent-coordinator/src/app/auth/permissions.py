"""
Permissions and Role-Based Access Control for AITBC Agent Coordinator.

.. deprecated::
    This module is a backward-compatibility shim. The canonical implementation
    lives in ``aitbc.auth.permissions``. Import from ``aitbc.auth`` directly
    in new code.
"""

import warnings

from aitbc.auth.permissions import (
    Permission,
    PermissionManager,
    Role,
    RolePermission,
    permission_manager,
)

warnings.warn(
    "app.auth.permissions is deprecated; import from aitbc.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "Permission",
    "PermissionManager",
    "Role",
    "RolePermission",
    "permission_manager",
]
