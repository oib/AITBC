# Database documentation

The earlier contents of this directory (RLS guides, a data dictionary) were
a foreign PostgreSQL/Prisma template — deleted; AITBC does not use row-level
security.

What is real:

- **Chain schema**: [docs/apps/blockchain-node/SCHEMA.md](../apps/blockchain-node/SCHEMA.md)
  — the chain.db tables as deployed.
- **Migrations**: `coordinator-api` runs `alembic upgrade head` at service
  start (`ExecStartPre`); migration sources live under
  `apps/coordinator-api/alembic/versions/`. A failed migration fails the start —
  check `journalctl -u aitbc-coordinator-api` first when it won't come up.
  `001_initial_migration` is a **frozen baseline**: explicit `create_table` /
  `create_index` DDL for the whole schema at commit `f7df5b478` (it used to
  call `SQLModel.metadata.create_all`, so fresh installs silently tracked
  whatever the models declared). It only ever runs on databases with no
  alembic version stamp — deployed databases are never re-stamped or rebuilt.
  To regenerate it after deliberately rebasing the baseline: stamp an empty
  scratch database to head, run `alembic revision --autogenerate`, fold the
  emitted body into `001` keeping `if_not_exists=True` on every create, and
  let `test_b8_schema_conformance.py` verify convergence.
- **Model layer**: SQLAlchemy/SQLModel (`aitbc/database/`, service
  `storage.py` modules); SQLite is the default store.
