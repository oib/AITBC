# Backup & restore runbook

How to take a consistent copy of a live AITBC node, verify it, and rebuild a
node from it. Validated by a live drill on 2026-10-13
(`TOPOLOGY/2026-10-13-backup-drill.md`): an operator-held chain DB copy passed
`PRAGMA integrity_check`, matched the live chain at 4 sampled heights, and
loaded under the node's own model layer.

## What to back up

Per host, in order of what hurts most to lose:

| data | where it lives | covered by `aitbc-backup.timer`? |
|---|---|---|
| chain DB | `/var/lib/aitbc/data/<island>/chain.db` | yes — `sqlite3 .dump` → `chain_*.db.gz` |
| coordinator DB | postgres `aitbc_*` databases | yes — `pg_dump` → `postgres_*.sql.gz` (where the DBs exist) |
| marketplace/service SQLite DBs | under `CHAIN_DB_DIR` (`*.db`) | yes — same `.dump` sweep |
| keystore + wallets | keystore dir, wallets dir, `/root/.aitbc/wallets` (legacy) | yes — `keystore.tar.gz`, `wallets.tar.gz` |
| env files | `/etc/aitbc/*.env` | yes — `etc-aitbc.tar.gz` |
| redis state | `redis.rdb` | yes — `BGSAVE` + copy |

The nightly timer lands at `/var/backups/aitbc/YYYYMMDD_HHMMSS/` on the same
host and prunes at `RETENTION_DAYS` (default 30). Two hooks exist but are
unset fleet-wide: `BACKUP_GPG_RECIPIENT` (encrypt the key-material tarballs)
and `BACKUP_OFFSITE_SCRIPT` (ship `$BACKUP_DIR` off the host). Both gaps are
documented in the drill record.

## Taking a consistent copy of a live chain DB

The chain DB runs in WAL mode. **Never `cp` a live `.db` file** — a raw copy
can catch the main file mid-checkpoint while transactions still sit in the
`-wal`, producing a torn or stale image. Use one of:

```bash
# Option A — SQLite online backup API (preferred: minimal read footprint,
# preserves pages as they are):
sqlite3 /var/lib/aitbc/data/<island>/chain.db \
  ".backup '/var/backups/aitbc/manual/chain-$(date +%Y%m%d-%H%M%S).db'"

# Option B — VACUUM INTO (also defragments; slower, result is checkpoint-free):
sqlite3 /var/lib/aitbc/data/<island>/chain.db \
  "VACUUM INTO '/var/backups/aitbc/manual/chain-$(date +%Y%m%d-%H%M%S).db'"
```

Both run inside SQLite's own locking, so the copy is a consistent snapshot of
a committed state. Copying a `-wal`/`-shm` alongside the `.db` is only needed
when the service is stopped; for a live copy, let SQLite produce the snapshot.

Inspecting a live DB read-only: prefer `mode=ro` and short, niced queries.
Never open a live WAL DB with `immutable=1` — that asserts there is no WAL and
silently ignores everything in it.

## Verifying a copy

On the destination, before trusting it:

```bash
sha256sum <source.db>            # compare with the remote hash after transfer
sqlite3 "file:copy.db?mode=ro" "PRAGMA integrity_check;"   # expect: ok
sqlite3 "file:copy.db?mode=ro" "PRAGMA quick_check;"       # expect: ok
sqlite3 "file:copy.db?mode=ro" "SELECT COUNT(*), MAX(height) FROM block;"
```

Then compare the head against a live node:

```bash
H=$(sqlite3 "file:copy.db?mode=ro" "SELECT MAX(height) FROM block;")
sqlite3 "file:copy.db?mode=ro" "SELECT hash, parent_hash FROM block WHERE height=$H;"
curl -s "http://127.0.0.1:8202/rpc/block/$H"   # compare hash + parent_hash
```

A backup that hash-matches the live chain at its head is a proven,
canonical-history prefix. Sample a few earlier heights too — the drill used
heights spread across the range and all four matched.

## Restoring on a replacement node

1. Stop the node's AITBC services on the replacement host.
2. Place the verified copy at the chain path:
   `install -m 600 -o root copy.db /var/lib/aitbc/data/<island>/chain.db`
   (remove any stale `chain.db-wal`/`chain.db-shm` next to it).
3. Start the node. Schema repair is built into startup:
   `chain_metadata.create_all` plus `_migrate_existing_columns` adds missing
   columns additively. The drill backup predated `block.aux_state_root` and
   carried no `alembic_version` table; startup repair covers that drift — the
   node does **not** run `alembic upgrade` on the chain DB at start (that is a
   manual step via `DATABASE_URL`), so no version stamp is required.
4. Confirm the node resumes: `curl -s http://127.0.0.1:8202/rpc/height` should
   report the restored height and then advance as sync catches up.
5. Restore the other data types from the same backup generation:
   `postgres_*.sql.gz` via `psql`, `keystore.tar.gz`/`wallets.tar.gz` into
   place (check ownership and modes), `etc-aitbc.tar.gz` into `/etc/aitbc`
   with per-service review, `redis.rdb` into the redis dir before redis
   starts.

Nightly artifacts under `/var/backups/aitbc/` are `sqlite3 .dump` output —
SQL text, not a DB file. Rebuild from them with
`zcat chain_<name>.db.gz | sqlite3 restored.db`, then run the same
verification block. Operator file copies (like the drill file) can be used
directly.

## Off-site pull

The fleet-side `BACKUP_OFFSITE_SCRIPT` hook stays unset **on purpose**: this
deployment uses a pull model — no fleet host holds credentials for the
destination, and nothing inbound needs to reach the hosts. The operator's
machine pulls each host's newest complete generation over the existing ssh
aliases with `scripts/ops/offsite-pull-backups.sh`.

What is pulled: the newest generation dir under `/var/backups/aitbc/` that
has been untouched for `STABLE_MIN` (10) minutes — the nightly job finishes
in under a minute at ~01:0x, so the 02:30 pull always sees a complete one.
Where it lands: `DEST/<host>/<generation>/` (default
`~/windsurf/aitbc/backups/fleet-nightly/`), staging at `<gen>.partial/` until
the sha256 manifest — computed on the host in the same ssh session that
picked the generation — verifies. Every pulled file is then stored
**age-encrypted** (`<name>.age`, including `SHA256SUMS.age` carrying the
plaintext manifest for restore-time re-verification); plaintext staging is
removed. `AGE_RECIPIENT` is required — the script refuses to store plaintext.
Keep the age **identity** file separately; it is the only thing that can
decrypt the pulls.

Retention: newest `KEEP` (14) name-matched generations per host; the newest
verified generation is never deleted; foreign directory names are never
touched. A 20 GB free-space floor (`MIN_FREE_GB`) is enforced before pulling.

Verify a pulled generation after decrypt:

```bash
age -d -i <identity> <host>/<gen>/SHA256SUMS.age > SHA256SUMS
for f in *.age; do age -d -i <identity> "$f" > "${f%.age}"; done
sha256sum -c SHA256SUMS   # all files OK
```

Restore from a pulled generation: decrypt to a scratch dir, then follow the
ordinary restore path above — `zcat chain_*.db.gz | sqlite3 chain.db` for the
dump artifacts (or use the file directly when it is already a DB file),
`integrity_check`, hash-compare, place at the chain path, start.

### Install (operator, on the pull host)

```bash
# one-time: create the identity that owns AGE_RECIPIENT (keep it safe &
# separate -- it decrypts every pulled generation)
age-keygen -o ~/.config/aitbc-backup-age-identity.txt
# -> prints "Public key: age1..."; that line's key is AGE_RECIPIENT

mkdir -p ~/.config/systemd/user
cp scripts/ops/offsite-pull-backups.{service,timer} ~/.config/systemd/user/
# edit the service's Environment=AGE_RECIPIENT= to the public key
systemctl --user daemon-reload
systemctl --user enable --now offsite-pull-backups.timer
journalctl --user -u offsite-pull-backups   # read the last run

# only if the timer should also run while the operator is logged out:
loginctl enable-linger oib
```

## Schedule and retention — recommendation

- **Keep the existing nightly timer** (`aitbc-backup.timer`, ~01:00 + splay,
  30-day retention) — it already covers every data type above on all five
  hosts. Changing cadence is not justified by the drill.
- **Add off-site copies**: the timer's `BACKUP_OFFSITE_SCRIPT` hook is the
  intended path; nightly pull or push of the latest generation to a second
  host (or the IDE host) closes the single-host-loss gap. Until then, the
  operator's manual copies are the only off-fleet recovery point.
- **Encrypt key-material archives** by setting `BACKUP_GPG_RECIPIENT` so
  `keystore.tar.gz`/`wallets.tar.gz`/`etc-aitbc.tar.gz` are not stored
  unencrypted alongside the data they protect.
- **Retention**: keep 30 days on-host plus the operator's off-fleet copies as
  the long-tail archive; one full verified generation per month off-host is a
  reasonable floor.

## Drill checklist (repeat quarterly or after schema migrations)

1. Pick a generation, copy it to scratch (0700 dir, file 0600).
2. `sha256sum` before and after transfer.
3. `integrity_check` + `quick_check` = `ok`.
4. Compare head hash + 3 sampled heights against live RPC.
5. Open read-only through the app's own model layer; note column drift that
   startup repair will additively fix.
6. Record timings and age; delete the scratch copy; write the drill record.
