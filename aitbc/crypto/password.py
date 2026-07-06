"""
Password hashing and validation utilities.

.. deprecated::
    This module is a backward-compatibility shim. The canonical implementation
    lives in ``aitbc.auth.password``. Import from ``aitbc.auth`` directly
    in new code.
"""

import warnings

from aitbc.auth.password import hash_password_pbkdf2 as hash_password, verify_password_pbkdf2 as verify_password

warnings.warn(
    "aitbc.crypto.password is deprecated; import from aitbc.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["hash_password", "verify_password"]
