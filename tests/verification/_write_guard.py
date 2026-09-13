"""Hold the ``__main__`` blocks in this directory to the same opt-in pytest is held to.

Every module here that POSTs also carries an ``if __name__ == "__main__"`` block that performs
exactly those writes. ``conftest.py`` never loads on that path -- a collection hook only exists
inside a pytest session -- so the gate that covers ``pytest tests/`` does not cover
``python tests/verification/test_minimal.py``, which is how a file shaped like a script gets
run.

Six of those scripts currently die on a relative import before reaching the network. That
looks like safety and is not: it is one import fix away from importing blocks again. The other
three reach the network today -- ``test_payment_integration.py`` gets as far as a live
coordinator, and ``register_test_clients.py`` and ``test_payment_local.py`` write to whatever
is listening on localhost.

Call ``require_opt_in`` as the first statement of the ``__main__`` block. Importing it there
rather than at module scope keeps it off the collection path entirely, and means the import
resolves against the script's own directory when run directly.
"""

from __future__ import annotations

import os
import sys

#: Must match ``conftest.ALLOW_ENV``. Asserted by
#: ``tests/test_production_host_gate.py::test_the_script_guard_shares_the_pytest_opt_in``.
ALLOW_ENV = "AITBC_ALLOW_PRODUCTION_WRITE_TESTS"


def require_opt_in(script: str) -> None:
    """Exit unless the caller has opted in, the same way the pytest gate requires."""
    if os.environ.get(ALLOW_ENV) == "1":
        return

    name = os.path.basename(script)
    sys.exit(
        f"{name}: refusing to run.\n"
        f"This writes blocks, jobs or miner results to whatever node it is pointed at -- by "
        f"default the one you are standing on -- and the writes persist: the rollback in "
        f"conftest is itself opt-in.\n"
        f"Set {ALLOW_ENV}=1 to run it deliberately."
    )
