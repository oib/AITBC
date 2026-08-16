"""The metadata this package's tables live on.

Every SQLModel class in the repo registers its `Table` on one process-global `MetaData` unless
it says otherwise, and the chain is not the only thing in this repo with a `Transaction`:
`apps/coordinator-api` has one too, along with its own `Block` and `Receipt`. Same registry,
same names, different columns.

The two never met in production -- the node and the coordinator are separate processes against
separate databases -- so what the collision broke was every attempt to test them together, and
the two workarounds it grew were the most destructive things in the test suite:

* `tests/integration/conftest.py` called `SQLModel._sa_registry.dispose()` and
  `SQLModel.metadata.clear()` at module scope, wiping the registry at collection time.
* `apps/blockchain-node/tests/conftest.py` removed every table it did not own from the global
  metadata before each of its own tests.

Both are process-wide and permanent. A class registers its `Table` when its module first
executes, and the module then stays in `sys.modules`, so re-importing re-registers nothing --
a table removed that way is gone for the rest of the run, and suites collected afterwards built
schemas with tables missing from them. That is what left six restored coordinator-api files
failing on "no such table: users" while passing in isolation (V23-71b, V23-72).

Declaring a private metadata here lets the two definitions coexist without either editing the
other, and both hooks come out. Table names, columns, constraints and indexes are unchanged;
`database.py` and `migrations/env.py` point here rather than at `SQLModel.metadata` (V23-74).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlmodel import SQLModel

chain_metadata = MetaData()


class ChainBase(SQLModel):
    """Declarative base for this package. Subclass instead of `SQLModel` for a table model."""

    metadata = chain_metadata
