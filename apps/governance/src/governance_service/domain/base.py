"""The metadata this service's tables live on.

Every SQLModel class in the repo registers on one process-global `MetaData` unless it says
otherwise, and this service is not the only one modelling governance: `apps/coordinator-api`
has its own bounded context defining `governance_profiles`, `proposals`, `votes`,
`dao_treasury` and `transparency_reports` under those same names. Two services, one registry,
five shared names -- so whichever imported second raised `Table '...' is already defined for
this MetaData instance` and the two could never be imported into one process (V23-72).

Nothing broke in production, where each service runs alone against its own database. What it
broke was every attempt to test them together, and the workarounds cost more than the
collision: `tests/integration/conftest.py` cleared the global metadata at import, and
`apps/blockchain-node/tests/conftest.py` removed every table it did not own before each of its
tests. Both mutations are process-wide and permanent -- a class registers its `Table` when its
module first executes, and the module then stays in `sys.modules`, so a table removed that way
never comes back. Suites collected afterwards built schemas with tables missing from them.

This service owns its tables, so it declares its own metadata and stops taking part. The
schemas are not affected: table names, columns, constraints and indexes are unchanged, and the
two definitions were already distinct objects that merely could not coexist. `storage.init_db`
and `alembic/env.py` both point here rather than at `SQLModel.metadata`.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlmodel import SQLModel

governance_metadata = MetaData()


class GovernanceBase(SQLModel):
    """Declarative base for this service. Subclass instead of `SQLModel` for a table model."""

    metadata = governance_metadata
