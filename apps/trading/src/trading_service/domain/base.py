"""The metadata this service's tables live on.

`apps/coordinator-api` carries a trading bounded context of its own under
`contexts/trading/domain/trading.py`, with the same table names. Both registered on SQLModel's
one process-global `MetaData` by default, and the previous answer was
`__table_args__ = {"extend_existing": True}` on all nine models here.

That does not give each service its own table. It merges the second definition into whichever
`Table` registered first, so whoever imports second silently redefines the first service's
columns, and the merge appends `Index` objects whose names are already on the table --
`create_all` then emits `CREATE INDEX ix_trade_negotiations_match_id` twice and the second one
fails. The failure had been hidden rather than absent: `tests/integration/conftest.py` cleared
the global metadata at collection, so only one of the two definitions was ever left standing.
Removing that clear (V23-74) is what surfaced it.

Declaring a private metadata gives this service its own tables and lets the duplicate
definitions coexist. Table names, columns, constraints and indexes are unchanged.
`alembic/env.py` points here; `storage.init_db` deliberately creates nothing, because schema
management is Alembic's job for this service.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlmodel import SQLModel

trading_metadata = MetaData()


class TradingBase(SQLModel):
    """Declarative base for this service. Subclass instead of `SQLModel` for a table model."""

    metadata = trading_metadata
