"""Path setup for the fast security-pin tier.

Each pin file imports the app module that owns the security property under
test; the app ``src`` directories are not installed into the root venv, so
they are added here once instead of per-file.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

for _app in ("coordinator-api", "api-gateway", "blockchain-node"):
    _src = str(_REPO_ROOT / "apps" / _app / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
