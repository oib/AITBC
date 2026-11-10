"""Make this app importable without disturbing how the rest of the suite is named.

`main.py`, `chain_client.py` and `routers/` live at the app root rather than under `src/`, so the app directory
has to be on `sys.path` for the tests to import them at all.

Two things keep that safe, and both matter (V23-69):

- The entry inserted is the *app* directory, never `apps/`. `apps/` is an ancestor of every
  app's test directory, so putting it on `sys.path` changes the module name pytest derives for
  every other suite and gets one conftest imported twice under two names.
- This `tests/` directory is deliberately not a package. With the app directory on `sys.path`
  and an `__init__.py` here, pytest would name these modules `tests.test_...` — colliding with
  the repo-root `tests` package, which is already in `sys.modules`.
"""

import importlib.util
import os
import sys
from pathlib import Path

# The suite runs as a configured service: chain-id resolution fails loudly
# without one since #307, so tests pin an explicit test id up front.
os.environ.setdefault("CHAIN_ID", "ait-testchain")

_APP_ROOT = str(Path(__file__).resolve().parent.parent)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# Load the app under a unique module name and register it for the test
# modules' ``from aitbc_explorer_main import app``. A bare ``import main``
# would collide in sys.modules with the other root-layout apps that ship
# their own main.py (hermes_agent, ollama_gate, ffmpeg, whisper) — whoever
# imports first wins and the loser's suite gets the wrong FastAPI app
# (#1657). Same convention as apps/ffmpeg/tests/test_smoke.py. ``main.py``'s
# own imports (``chain_client``, ``routers.*``) still resolve through
# _APP_ROOT on sys.path above.
_main_spec = importlib.util.spec_from_file_location("aitbc_explorer_main", Path(_APP_ROOT) / "main.py")
assert _main_spec is not None and _main_spec.loader is not None
_explorer_main = importlib.util.module_from_spec(_main_spec)
sys.modules["aitbc_explorer_main"] = _explorer_main
_main_spec.loader.exec_module(_explorer_main)
