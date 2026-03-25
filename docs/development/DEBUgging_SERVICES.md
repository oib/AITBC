# Debugging Services — aitbc1

**Date:** 2026-03-13
**Branch:** aitbc1/debug-services

## Status

- [x] Fixed CLI hardcoded paths; CLI now loads
- [x] Committed robustness fixes to main (1feeadf)
- [x] Patched systemd services to use /opt/aitbc paths
- [x] Installed coordinator-api dependencies (torch, numpy, etc.)
- [ ] Get coordinator-api running (DB migration issue)
- [ ] Get wallet daemon running
- [ ] Test wallet creation and chain genesis
- [ ] Set up P2P peering between aitbc and aitbc1

## Blockers

### Coordinator API startup fails
```
sqlalchemy.exc.OperationalError: index ix_users_email already exists
```
Root cause: migrations are not idempotent; existing DB has partial schema.
Workaround: use a fresh DB file.

Also need to ensure .env has proper API key lengths and JSON array format.

## Next Steps

1. Clean coordinator.db, restart coordinator API successfully
2. Start wallet daemon (simple_daemon.py)
3. Use CLI to create wallet(s)
4. Generate/use genesis_brother_chain_1773403269.yaml
5. Start blockchain node on port 8005 (per Andreas) with that genesis
6. Configure peers (aitbc at 10.1.223.93, aitbc1 at 10.1.223.40)
7. Send test coins between wallets

## Notes

- Both hosts on same network (10.1.223.0/24)
- Services should run as root (no sudo needed)
- Ollama available on both for AI tests later
