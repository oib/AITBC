"""
Secure pickle deserialization utilities to prevent arbitrary code execution.
"""

import pickle
import io
from typing import Any

# Safe classes whitelist: builtins and common types
SAFE_MODULES = {
    'builtins': {
        'list', 'dict', 'set', 'tuple', 'int', 'float', 'str', 'bytes',
        'bool', 'NoneType', 'range', 'slice', 'memoryview', 'complex'
    },
    'datetime': {'datetime', 'date', 'time', 'timedelta', 'timezone'},
    'collections': {'OrderedDict', 'defaultdict', 'Counter', 'namedtuple'},
    'dataclasses': {'dataclass'},
    'typing': {'Any', 'List', 'Dict', 'Tuple', 'Set', 'Optional', 'Union', 'TypeVar', 'Generic', 'NamedTuple', 'TypedDict'},
}

class RestrictedUnpickler(pickle.Unpickler):
    """
    Unpickler that restricts which classes can be instantiated.
    Only allows classes from SAFE_MODULES whitelist.
    """
    def find_class(self, module: str, name: str) -> Any:
        if module in SAFE_MODULES and name in SAFE_MODULES[module]:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"Class {module}.{name} is not allowed for unpickling (security risk).")

def safe_loads(data: bytes) -> Any:
    """Safely deserialize a pickle byte stream."""
    return RestrictedUnpickler(io.BytesIO(data)).load()
