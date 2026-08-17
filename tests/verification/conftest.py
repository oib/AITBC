"""Keep the production-probing verification scripts out of automated runs.

Several files in this directory are not unit tests. They point at the live deployment --
`BASE_URL = "https://hub.aitbc.bubuit.net/rpc"` and
`COORDINATOR_URL = "https://hub.aitbc.bubuit.net/api"` -- read the current head, and then
POST: newly constructed blocks to `/rpc/importBlock`, jobs to `/v1/jobs`, miner results to
`/v1/miners/{id}/result`. A passing run means blocks were accepted into production and real
jobs and payments were created there. They are named `test_*.py`, so any `pytest tests/`
picks them up and tries exactly that.

**The list used to be hand-maintained and was wrong.** It named three modules; seven name
the production host and all seven write to it. `test_minimal.py`, `test_simple_import.py`
and `test_tx_import.py` each POST to `/importBlock`, and `test_payment_integration.py`
creates jobs, polls as a miner, submits results and triggers a refund -- none of them
gated. A list that has to be updated by hand every time a file is added is a list that will
be wrong again, so the gate now reads the file instead: any module whose source names a
deployment host is skipped, and a new file naming one is covered the day it lands.

Matching on source text is deliberately blunt. It over-matches -- a module that only
mentions the host in a comment is skipped too -- and that is the right direction to err.
It also reads the file rather than importing it, so nothing in a gated module executes.

**The gate has to be confined to this directory** (V23-93). `pytest_collection_modifyitems`
is handed the whole session's item list no matter which `conftest.py` defines it, so for one
release the blunt text match ran against every file in the repository: 159 ordinary unit
tests were skipped for naming the host in a URL constant or a docstring, among them the
`/coin-requests/execute` authorization tests and the invocation-safety tests for the 3600x
balance migration. Over-matching is the right direction to err *here*, where every module
really does write to production; applied repo-wide it silently turned off the tests that
verify the protections. Hence `_is_in_this_directory`.

Set ``AITBC_ALLOW_PRODUCTION_WRITE_TESTS=1`` to run them, which makes running them a
deliberate act. The rest of this directory -- the import-surface checks, the model
validation, the localhost payment flow -- is ordinary and runs normally.

These want rewriting against a local node fixture rather than a hostname in a constant;
that is a larger change than gating them.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

#: Hosts that are somebody's live deployment. Matched against module source, not resolved.
PRODUCTION_HOST_RE = re.compile(r"\bbubuit\.net\b")

ALLOW_ENV = "AITBC_ALLOW_PRODUCTION_WRITE_TESTS"

#: The only directory this gate speaks for. See the module docstring: the hook itself is
#: repo-wide, so the boundary has to be enforced here rather than assumed from placement.
GATED_DIR = Path(__file__).resolve().parent


def _is_in_this_directory(path) -> bool:  # noqa: ANN001 - pytest hands us its own path type
    """Whether the item lives under `tests/verification/`."""
    try:
        resolved = Path(str(path)).resolve()
    except OSError:
        return False
    return resolved == GATED_DIR or GATED_DIR in resolved.parents


def _names_production_host(path) -> bool:  # noqa: ANN001 - pytest hands us its own path type
    """Whether this file's source mentions a deployment host at all."""
    try:
        return PRODUCTION_HOST_RE.search(path.read_text(encoding="utf-8", errors="ignore")) is not None
    except OSError:
        # Unreadable means unknown, and unknown is treated as production-touching.
        return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(ALLOW_ENV) == "1":
        return

    skip = pytest.mark.skip(
        reason=(
            f"Names a live deployment host and this directory's modules write to it "
            f"(blocks, jobs, miner results). Set {ALLOW_ENV}=1 to run deliberately."
        )
    )

    gated: dict[str, bool] = {}
    for item in items:
        path = getattr(item, "path", None)
        if path is None:
            continue
        key = str(path)
        if key not in gated:
            gated[key] = _is_in_this_directory(path) and _names_production_host(path)
        if gated[key]:
            item.add_marker(skip)
