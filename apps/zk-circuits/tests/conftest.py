"""Make this app importable without disturbing how the rest of the suite is named.

`zk_cache.py` and `compile_cached.py` live at the app root rather than under `src/`, so the app directory
has to be on `sys.path` for the tests to import them at all.

Two things keep that safe, and both matter (V23-69):

- The entry inserted is the *app* directory, never `apps/`. `apps/` is an ancestor of every
  app's test directory, so putting it on `sys.path` changes the module name pytest derives for
  every other suite and gets one conftest imported twice under two names.
- This `tests/` directory is deliberately not a package. With the app directory on `sys.path`
  and an `__init__.py` here, pytest would name these modules `tests.test_...` — colliding with
  the repo-root `tests` package, which is already in `sys.modules`.
"""

import sys
from pathlib import Path

_APP_ROOT = str(Path(__file__).resolve().parent.parent)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)
