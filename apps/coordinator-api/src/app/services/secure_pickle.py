"""
Secure pickle deserialization utilities to prevent arbitrary code execution.
"""

import importlib.util
import io
import os
import pickle
from typing import Any

from aitbc import REPO_DIR

# Safe classes whitelist: builtins and common types
SAFE_MODULES = {
    "builtins": {
        "list",
        "dict",
        "set",
        "tuple",
        "int",
        "float",
        "str",
        "bytes",
        "bool",
        "NoneType",
        "range",
        "slice",
        "memoryview",
        "complex",
    },
    "datetime": {"datetime", "date", "time", "timedelta", "timezone"},
    "collections": {"OrderedDict", "defaultdict", "Counter", "namedtuple"},
    "dataclasses": {"dataclass"},
}

# Compute trusted origins: site-packages inside the venv and stdlib paths
_ALLOWED_ORIGINS = set()


def _initialize_allowed_origins():
    """Build set of allowed module file origins (trusted locations)."""
    # 1. All site-packages directories that are under the application venv
    for entry in os.sys.path:
        if "site-packages" in entry and os.path.isdir(entry):
            # Only include if it's inside the AITBC repository
            if str(REPO_DIR) in entry:  # restrict to our app directory
                _ALLOWED_ORIGINS.add(os.path.realpath(entry))
    # 2. Standard library paths (typically without site-packages)
    # We'll allow any origin that resolves to a .py file outside site-packages and not in user dirs
    # But simpler: allow stdlib modules by checking they come from a path that doesn't contain 'site-packages' and is under /usr/lib/python3.13
    # We'll compute on the fly in find_class for simplicity.


_initialize_allowed_origins()


class RestrictedUnpickler(pickle.Unpickler):
    """
    Unpickler that restricts which classes can be instantiated.
    Only allows classes from SAFE_MODULES whitelist and verifies module origin
    to prevent shadowing by malicious packages.
    """

    def find_class(self, module: str, name: str) -> Any:
        if module in SAFE_MODULES and name in SAFE_MODULES[module]:
            # Verify module origin to prevent shadowing attacks
            spec = importlib.util.find_spec(module)
            if spec and spec.origin:
                origin = os.path.realpath(spec.origin)
                # Allow if it's from a trusted site-packages (our venv)
                for allowed in _ALLOWED_ORIGINS:
                    if origin.startswith(allowed + os.sep) or origin == allowed:
                        return super().find_class(module, name)
                # Allow standard library modules (outside site-packages and not in user/local dirs)
                if "site-packages" not in origin and ("/usr/lib/python" in origin or "/usr/local/lib/python" in origin):
                    return super().find_class(module, name)
                # Reject if origin is unexpected (e.g., current working directory, /tmp, /home)
                raise pickle.UnpicklingError(f"Class {module}.{name} originates from untrusted location: {origin}")
            else:
                # If we can't determine origin, deny (fail-safe)
                raise pickle.UnpicklingError(f"Cannot verify origin for module {module}")
        raise pickle.UnpicklingError(f"Class {module}.{name} is not allowed for unpickling (security risk).")


def safe_loads(data: bytes) -> Any:
    """Safely deserialize a pickle byte stream."""
    return RestrictedUnpickler(io.BytesIO(data)).load()


# ... existing code ...


def _lock_sys_path():
    """Replace sys.path with a safe subset to prevent shadowing attacks."""
    import sys

    if isinstance(sys.path, list):
        trusted = []
        for p in sys.path:
            # Keep site-packages under REPO_DIR (our venv)
            if "site-packages" in p and str(REPO_DIR) in p:
                trusted.append(p)
            # Keep stdlib paths (no site-packages, under /usr/lib/python)
            elif "site-packages" not in p and ("/usr/lib/python" in p or "/usr/local/lib/python" in p):
                trusted.append(p)
            # Keep our application directory
            elif p.startswith(str(REPO_DIR / "apps" / "coordinator-api")):
                trusted.append(p)
        sys.path = trusted


# Lock sys.path immediately upon import to prevent later modifications
_lock_sys_path()
