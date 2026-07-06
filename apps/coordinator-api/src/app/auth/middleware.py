"""
Auth middleware for automatic route protection.

.. deprecated::
    This module is a backward-compatibility shim. The canonical implementation
    lives in ``aitbc.auth.middleware``. Import from ``aitbc.auth`` directly
    in new code.
"""

import warnings

from aitbc.auth.middleware import AuthMiddleware

warnings.warn(
    "app.auth.middleware is deprecated; import from aitbc.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["AuthMiddleware"]
