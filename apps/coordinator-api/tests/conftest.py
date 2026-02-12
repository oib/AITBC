"""Ensure coordinator-api src is on sys.path for all tests in this directory."""

import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent.parent / "src")

# Remove any stale 'app' module loaded from a different package so the
# coordinator 'app' resolves correctly.
_app_mod = sys.modules.get("app")
if _app_mod and hasattr(_app_mod, "__file__") and _app_mod.__file__ and _src not in str(_app_mod.__file__):
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]

if _src not in sys.path:
    sys.path.insert(0, _src)
