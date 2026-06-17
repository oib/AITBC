# Operational Fixes - v0.4.16

**Release**: v0.4.16
**Date**: June 12, 2026
**Status**: ✅ Released

## Overview

AITBC v0.4.16 resolves operational issues with systemd, backup scripts, logging, and keystore permissions.

## 1. Fixed Systemd MemoryLimit Deprecation

- `/etc/systemd/system/aitbc-blockchain-rpc.service`: Removed deprecated `MemoryLimit=512M` directive (already had `MemoryMax=512M`)

## 2. Fixed Backup Script PostgreSQL Authentication

- `scripts/maintenance/aitbc-backup.sh`: Removed hardcoded `PGPASSWORD="aitbc_governance_pass"` password
- Added automatic sourcing of `/etc/aitbc/blockchain-secrets.env` for `PGPASSWORD`
- Added clear error when `PGPASSWORD` is unset with instructions

## 3. Fixed P2P Network Logging

- `apps/blockchain-node/src/aitbc_chain/p2p_network.py`: Changed logger name from `__main__` to `aitbc_chain.p2p_network` for readable journalctl output
- Added systemd detection (`INVOCATION_ID`) to strip duplicate `%(asctime)s` timestamp from formatter

## 4. Fixed Keystore Permissions and Proposer Key Loading

- `/var/lib/aitbc/keystore/`: Fixed `drwx------` → `drwxr-x---` and `.password` `rw-------` → `rw-r-----` so `aitbc-blockchain:aitbc-services` can read
- `apps/blockchain-node/src/aitbc_chain/main.py`: Rewrote `_load_private_key_from_keystore` to support simple wallet JSON format and encrypted private keys via `aitbc.crypto.decrypt_private_key`
- Created `/var/lib/aitbc/keystore/proposer.json` with genesis wallet private key for block signing

---

*Last Updated: 2026-06-12*
