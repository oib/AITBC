# Bridge outbound-ledger migration — live runbook (BR-6 phase C)

> **Status: NOT AUTHORIZED.** This runbook describes the live migration
> only. Executing it requires a typed operator line; the 12 Oct operator
> decision keeps it closed — revisit with BR-1 or before mainnet.

## What the migration is

B13 (`TOPOLOGY/2026-10-08-b13-bridge-outbound-ledger-design.md`) adds a
`bridge_outbound` table to the bridge ledger so outbound ETH (depositor
refunds, operator withdrawals, gas) stops being invisible to the reconcile.
Today `eth_deposits` records inflows only; `bridge_wallet_reconcile.py`
closes the books only with an operator-supplied `--onchain` document.

The migration is **additive and schema-only**: one `CREATE TABLE IF NOT
EXISTS` in `bridge_monitor/storage.py`'s `init_db()` bootstrap, same
PRAGMA-verify discipline as the existing column migrations. No existing
rows are touched, no data is rewritten. The *writer* (`record_outbound` at
the `from == bridge_eth_address` scan branch) ships with the same deploy
or a follow-up; the table alone changes nothing observable.

```sql
CREATE TABLE IF NOT EXISTS bridge_outbound (
    tx_hash       TEXT PRIMARY KEY,
    to_address    TEXT NOT NULL,
    value_eth     NUMERIC NOT NULL,
    gas_wei       INTEGER,
    block_height  INTEGER NOT NULL,
    kind          TEXT NOT NULL,            -- refund | withdrawal | unidentified
    matched_deposit_tx TEXT,
    note          TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Preconditions

- [ ] Typed operator line naming this migration, the host, and the restart.
- [ ] Hub on the intended deploy commit (`git -C /opt/aitbc rev-parse HEAD`).
- [ ] `aitbc-backup.service` ran since the last ledger write; the fresh
      `/var/backups/aitbc/<ts>/` directory lists `bridge_deposits.db`.
      If the last backup predates recent deposit traffic, trigger the job
      deliberately — do not copy the live file by hand (a hot sqlite copy
      can carry a partial page; the backup job does it safely).
- [ ] Confirm the DB path from the unit, never an env file:
      `systemctl cat aitbc-bridge-monitor | grep -iE 'data|db'`
      (default `/var/lib/aitbc/bridge_deposits.db` via
      `AITBC_DATA_DIR`→`DATA_DIR`→`/var/lib/aitbc`).
- [ ] `sqlite3 "file:<db>?mode=ro" "PRAGMA table_info(bridge_outbound)"`
      returns empty — table absent (else the migration already ran).
- [ ] `bridge_monitor.admin`/`aitbc` report no SUBMITTED payout in flight;
      a schema-only change is safe mid-flight but verifying first keeps the
      read clean.
- [ ] `scripts/ops/bridge_outbound_migration_dryrun.py` already proven —
      fixture run reconciles BALANCED (BR-7, commit `3e0949c00`).

## Steps

1. **Backup gate.** Confirm the timestamped backup row exists and is
   fresh; record its path in the ops log.
2. **Snapshot for verification queries only** (optional, never required):
   `sqlite3 "file:<db>?mode=ro" ".dump eth_deposits" > /tmp/pre.sql` —
   read-only dump for before/after diffing; not a restore source.
3. **Deploy.** `git pull` to the commit carrying the DDL in
   `init_db()`; `systemctl restart aitbc-bridge-monitor` — the bootstrap
   runs `CREATE TABLE IF NOT EXISTS` on start. The wallet service shares
   the same file and schema conventions; restart it only if its build
   carries the change too.
4. **Verify** (all read-only):
   ```bash
   sqlite3 "file:<db>?mode=ro" "PRAGMA table_info(bridge_outbound)"
   # columns: tx_hash, to_address, value_eth, gas_wei, block_height,
   #          kind, matched_deposit_tx, note, created_at
   sqlite3 "file:<db>?mode=ro" "SELECT COUNT(*) FROM bridge_outbound"
   sqlite3 "file:<db>?mode=ro" "SELECT COUNT(*) FROM eth_deposits"
   # deposit count identical to the pre-change read
   ```
5. **Journal check:** `journalctl -u aitbc-bridge-monitor --since -5min`
   — clean start, no OperationalError.
6. **Report** the head, the column listing, and the deposit-row count
   before/after.

## Downgrade

`bridge_outbound` is additive — dropping it restores the prior schema:

```bash
sqlite3 <db> "DROP TABLE bridge_outbound"   # only under an operator line
```

then revert the code to the pre-migration commit (`git revert` / pull to
the previous SHA) and restart the monitor. The table holds only derived
data; a rebuilt table re-derives from sealed chain rows plus the ledger,
so downgrade loses nothing that cannot be recomputed.

## Verification queries (acceptance)

- `PRAGMA table_info(bridge_outbound)` matches the nine columns above.
- `SELECT COUNT(*) FROM eth_deposits` unchanged across the restart.
- First outbound send after deploy lands a `bridge_outbound` row with the
  right `kind` (once the writer ships).
- `bridge_wallet_reconcile.py` reads the same deposit set as before —
  no count drift.

## Stop conditions — halt and report, do not improvise

- Backup missing or older than the last ledger write.
- `PRAGMA table_info` shows a partial table (fewer than nine columns) —
  drop nothing, report.
- Monitor fails to start after restart; ledger `sqlite3` reports
  `database is locked` for more than a few seconds.
- Any deposit row count change across the migration.
- Any `unidentified`-kind row inserted where a depositor match existed —
  report rather than reclassify.
- Anything prompting for a wallet password or key file: stop and ask.

## Boundaries

No key-bearing env file is read for any step (`exchange.env`,
bridge-monitor env). Address material needed by verification comes from
`cli/aitbc_cli/commands/eth.py` `DEFAULT_WALLETS` /
`docs/ops/node-sepolia-wallets.md` — public address data only.
