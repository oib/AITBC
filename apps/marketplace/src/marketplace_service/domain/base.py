"""The metadata this service's tables live on.

`apps/coordinator-api` carries a marketplace bounded context of its own, and the two overlap by
table name. Both registered on SQLModel's one process-global `MetaData` by default, so the
previous answer was `__table_args__ = {"extend_existing": True}` on all twelve models here.
That does not give each service its own table -- it merges the second definition into whichever
`Table` registered first, silently redefining the first service's columns and appending `Index`
objects whose names are already on the table, so `create_all` emits the same `CREATE INDEX`
twice and the second one fails (V23-72).

This service's own models therefore live here instead. `MarketplaceOffer` deliberately does
not: it comes from `packages/aitbc-shared` and is one class shared with coordinator-api rather
than a duplicate of one, so it stays on the global registry and `storage.init_db` names it
explicitly.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlmodel import SQLModel

marketplace_metadata = MetaData()


class MarketplaceBase(SQLModel):
    """Declarative base for this service. Subclass instead of `SQLModel` for a table model."""

    metadata = marketplace_metadata
