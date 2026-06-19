"""
DEPRECATED: Security utilities for AITBC

This module is deprecated. Use aitbc.security instead.

Migration guide:
- from aitbc.security_hardening import SecurityValidator → from aitbc.security import SecurityValidator
- from aitbc.security_hardening import SecurityAuditLog → from aitbc.security import SecurityAuditLog
- from aitbc.security_hardening import SecurityAuditor → from aitbc.security import SecurityAuditor
- from aitbc.security_hardening import RateLimiter → from aitbc.security import RateLimiter
"""

import warnings

# RateLimiter was not in the original security_hardening.py, but is now in aitbc.security
# We import it here for backward compatibility with code that might expect it
from aitbc.security import RateLimiter, SecurityAuditLog, SecurityAuditor, SecurityValidator

warnings.warn(
    "aitbc.security_hardening is deprecated, use aitbc.security instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "SecurityValidator",
    "SecurityAuditLog",
    "SecurityAuditor",
    "RateLimiter",
]
