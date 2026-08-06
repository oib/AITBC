"""Keep the production-probing verification scripts out of automated runs.

test_block_import.py and test_block_import_complete.py are not unit tests. They point at
BASE_URL = "https://hub.aitbc.bubuit.net/rpc" -- the live mainnet RPC -- read its current
head, and POST newly constructed blocks to /rpc/blocks/import. A passing run means blocks
were accepted into production. They are named test_*.py, so any `pytest tests/` picks them
up and tries exactly that.

They currently fail (the node reports "unable to open database file"), which is the only
reason a stray run has not been writing to mainnet. That is not a safeguard.

They are skipped unless AITBC_ALLOW_PRODUCTION_WRITE_TESTS=1 is set, so running them is a
deliberate act. The rest of tests/verification -- the import-surface checks -- is ordinary
and runs normally.

These two want rewriting against a local node fixture rather than a hostname in a
constant; that is a larger change than gating them.
"""

from __future__ import annotations

import os

import pytest

PRODUCTION_WRITE_MODULES = {
    "test_block_import",
    "test_block_import_complete",
    # test_cross_node_block_sync POSTs to /importBlock on the same live hub. It also
    # indexes NODES["aitbc1"], which is not in its own NODES dict, so it would KeyError
    # before finishing -- after the import call has already been made.
    "test_cross_node_blockchain",
}

ALLOW_ENV = "AITBC_ALLOW_PRODUCTION_WRITE_TESTS"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(ALLOW_ENV) == "1":
        return

    skip = pytest.mark.skip(
        reason=(f"Writes blocks to the live mainnet RPC (hub.aitbc.bubuit.net). Set {ALLOW_ENV}=1 to run deliberately.")
    )
    for item in items:
        if item.module is not None and item.module.__name__.rsplit(".", 1)[-1] in PRODUCTION_WRITE_MODULES:
            item.add_marker(skip)
