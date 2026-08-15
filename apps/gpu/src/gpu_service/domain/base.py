"""The metadata this service's tables live on.

`apps/coordinator-api` carries its own copy of these models under
`contexts/marketplace/domain/gpu_marketplace.py` -- same table names, same columns. Both
register on SQLModel's one process-global `MetaData` by default, so importing the two into a
single process used to raise `Table 'gpu_registry' is already defined`.

The previous answer was `__table_args__ = {"extend_existing": True}` on every model here, and
it is worth being precise about why that is worse than the error it silenced. `extend_existing`
does not give each service its own table; it merges the second definition into whichever
`Table` was registered first. Whoever imports second silently redefines the first service's
columns, and the merge appends `Index` objects that duplicate names already on the table, so
`create_all` emits `CREATE INDEX ix_gpu_reviews_created_at` twice and the second one fails.
That is not a hypothetical either -- it took out an unrelated test in `tests/integration` and
read as a flake, because the failure lands wherever `create_all` happens to run next rather
than where the two definitions met (V23-72).

Declaring a private metadata gives this service its own tables and lets the duplicate
definitions coexist without either editing the other. Table names, columns, constraints and
indexes are unchanged. `storage.init_db` and `alembic/env.py` both point here.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlmodel import SQLModel

gpu_metadata = MetaData()


class GpuBase(SQLModel):
    """Declarative base for this service. Subclass instead of `SQLModel` for a table model."""

    metadata = gpu_metadata
