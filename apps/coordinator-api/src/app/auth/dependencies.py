"""
Role-based authentication dependencies.

.. deprecated::
    This module is a backward-compatibility shim. The canonical implementation
    lives in ``aitbc.auth.dependencies``. Import from ``aitbc.auth`` directly
    in new code.
"""

import warnings

from aitbc.auth.dependencies import (
    AdminDep,
    AuthDep,
    ClientDep,
    MinerDep,
    get_token,
    require_admin,
    require_auth,
    require_client,
    require_miner,
    require_miner_api_key,
    require_miner_jwt,
)

warnings.warn(
    "app.auth.dependencies is deprecated; import from aitbc.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "AdminDep",
    "AuthDep",
    "ClientDep",
    "MinerDep",
    "get_token",
    "require_admin",
    "require_auth",
    "require_client",
    "require_miner",
    "require_miner_api_key",
    "require_miner_jwt",
]
