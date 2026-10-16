# Bridge outbound-ledger migration — live runbook (BR-6 phase C)

> **Status: EXECUTED 16 Oct 2026 on hub** (operator line, same day). Hub
> pulled to `818f237ad`, `aitbc-bridge-monitor` restarted at 12:21 UTC+2;
> `bridge_outbound` verified live (nine columns, 0 rows, `eth_deposits`
> unchanged at 9). Backup: `/var/backups/aitbc/20261016_122023/`
> (`bridge_deposits.db` captured via sqlite `.backup` — the daily job does
> not cover the DATA_DIR-root ledger file). Table fills on the next
> outbound send; historical legs remain in the BR-6 decomposed report.

## What the migration is

B13 (`TOPOLOGY/2026-10-08-b13-bridge-outbound-ledger-design.md` — staging
file only, no repo copy) adds a
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

- [ ] The code carrying the table exists: landed in `4abfe62cf`
      (`bridge_monitor/storage.py` `init_db()` + `record_outbound`,
      `wallet_app/bridge/bridge_db.py`, the scan-side writer in
      `main.py`, and the reconcile extension). Step 3 pulls exactly that
      commit (or a later reviewed one — record its SHA).
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
data — each row is written by the monitor's scan when it sees an outbound
Ethereum transaction sent *from* the bridge wallet (refund, withdrawal or
unidentified), so a rebuilt table re-derives from the Ethereum chain, not
from the ledger. One exception: the `note` column is operator annotation
(write-off reasons and the like) typed by a human — anything written there
is not recomputable and is lost on a drop.

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

## Bridge ledger path override (`BRIDGE_DEPOSITS_DB`)

Every consumer of the ledger — `bridge_monitor.storage`, the wallet's
`bridge_db` helpers (routes, settlement and withdraw monitors all funnel
through it), the exchange readiness check, `exchange_verify.py`/`aitbc
exchange verify --bridge-db`, and `fleet-config-check.sh` — honours the
`BRIDGE_DEPOSITS_DB` env var. Unset, each resolves exactly the default it
always did (`<data dir>/bridge_deposits.db`); explicit `--ledger`/`--db`
flags still win over the variable.

Set it for **every** consumer on a host or for **none**. `sqlite3.connect()`
creates an empty file at a missing path, so a consumer left on the old path
silently opens a fresh empty ledger — split-brain with no error. Scripts
that glob (`bridge-payout-audit.py`) or require `--ledger`
(`bridge_wallet_rotation_report.py`) follow their own rules and are exempt.

## Boundaries

No key-bearing env file is read for any step (`exchange.env`,
bridge-monitor env). Address material needed by verification comes from
`cli/aitbc_cli/commands/eth.py` `DEFAULT_WALLETS` /
`docs/ops/node-sepolia-wallets.md` — public address data only.

## Appendix — historical backfill (executed 16 Oct pending operator line)

Backfills the five outbound sends the monitor made *before* the writer
shipped. One reviewed transaction; nothing else writes.

### Preconditions

- [ ] Typed operator line naming the backfill INSERT on hub.
- [ ] Fresh backup artifact: `systemctl start aitbc-backup.service`, then
      confirm the newest `/var/backups/aitbc/<ts>/` lists a bridge-ledger
      artifact (BACKUP-1 sweeps DATA_DIR-root DBs since `c2c604339`).
- [ ] `bridge_outbound` is empty or contains none of the five tx_hashes:
      `sqlite3 "file:/var/lib/aitbc/bridge_deposits.db?mode=ro"
      "SELECT tx_hash FROM bridge_outbound"`.
- [ ] The row set reviewed from a regenerated `--emit-rows` output (tx
      list from Blockscout `txlist` for the bridge wallet, mode=ro
      ledger reads, funding sources from the unit env *names*).

### Procedure

```bash
# 1. Build the row set (read-only everywhere; emits JSON rows).
python3 scripts/ops/bridge_outbound_collect.py \
  --txs outbound_txs.json --ledger <scratch .backup of the DB> \
  --funding-json funding.json \
  --self-address 0x310dcE00270D0aC10CAccfBD636Ff07BD5648781 \
  --balance-wei <current> --emit-rows rows.json

# 2. Apply via the monitor's own writer path (INSERT OR IGNORE, one
#    transaction per row, deduped on tx_hash):
/opt/aitbc/venv/bin/python - <<'PYEOF'
import json, sys
sys.path.insert(0, "/opt/aitbc/apps/bridge-monitor/src")
from bridge_monitor.storage import record_outbound, init_db
init_db()
for r in json.load(open("rows.json")):
    ok = record_outbound(r["tx_hash"], r["to_address"],
        int(float(r["value_eth"]) * 10**18), r["block_height"], r["kind"],
        gas_wei=r["gas_wei"], matched_deposit_tx=r["matched_deposit_tx"], note=r["note"])
    print(r["tx_hash"][:14], "inserted" if ok else "already present")
PYEOF
```

### Verification (all read-only)

```bash
sqlite3 "file:<db>?mode=ro" "SELECT COUNT(*) FROM bridge_outbound"   # 5
sqlite3 "file:<db>?mode=ro" "SELECT COUNT(*) FROM eth_deposits"      # still 9
scripts/ops/bridge_wallet_reconcile.py --ledger <scratch copy> --onchain onchain.json
# expected: named residual, not BALANCED — see below
```

Expected verdict after insert: **DEFICIT ~0.052 ETH**, the already-
decomposed pre-rotation old-wallet outflows (`52335372406592269` wei in
the rotation fixture) — the five new rows explain 0.00184 ETH of named
outbound; the rest is the OLD wallet's history which a backfill of the
current wallet's txlist cannot cover. Two rows stay `unidentified`
(~0.000166 ETH to `0xcf17…`, node2's Sepolia wallet) — flagged for
operator review, not reclassified.

### Downgrade

Delete exactly the five inserted rows by tx_hash — additive rows only:

```sql
DELETE FROM bridge_outbound WHERE tx_hash IN
  ('0x914463b7…','0x7b7eaec3…','0x38b1fa33…','0xcbf5a1a8…','0xdaf4b9cf…')
```
