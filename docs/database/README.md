# Database documentation

The earlier contents of this directory (RLS guides, a data dictionary) were
a foreign PostgreSQL/Prisma template — deleted; AITBC does not use row-level
security.

What is real:

- **Chain schema**: [docs/apps/blockchain-node/SCHEMA.md](../apps/blockchain-node/SCHEMA.md)
  — the chain.db tables as deployed.
- **Migrations**: `coordinator-api` runs `alembic upgrade head` at service
  start (`ExecStartPre`); migration sources live under
  `apps/coordinator-api/migrations/`. A failed migration fails the start —
  check `journalctl -u aitbc-coordinator-api` first when it won't come up.
- **Model layer**: SQLAlchemy/SQLModel (`aitbc/database/`, service
  `storage.py` modules); SQLite is the default store.
