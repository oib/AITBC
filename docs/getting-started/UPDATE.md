# AITBC Update Guide

**Last Updated:** 2026-06-22

How to safely update an already-installed AITBC node after new code is
merged to `main`. For first-time installation, see
[SETUP.md](./SETUP.md) instead.

> **TL;DR**
> ```bash
> sudo /opt/aitbc/scripts/deployment/update.sh
> ```

## When to run `update.sh`

Run it whenever you want to apply new code changes from the `origin/main`
branch to a running node. Common triggers:

- After merging a PR to `main` and wanting to deploy it
- After seeing the `aitbc-backup.timer` fire and wanting to pick up new code
- After pulling manually and noticing a `setup.sh` change in the diff
- Any time `requirements.txt`, `cli/requirements-cli.txt`, or a
  `*.service` file changed on `main`

`update.sh` is **idempotent** — running it when nothing changed is safe
(it will print "Already up to date" and exit).

## Quick start

```bash
# Full update: backup, pull, sync venv, relink systemd, restart services, health check
sudo /opt/aitbc/scripts/deployment/update.sh
```

That's it for the common case. The script:

1. Backs up the node
2. Pulls the latest code
3. Syncs the Python venv
4. Relinks systemd unit files (role-aware)
5. Restarts all running aitbc services
6. Runs a health check
7. Prints a summary with manual follow-up reminders

## Flags

| Flag | Effect |
|---|---|
| `--no-pull` | Skip `git pull` (assume you already pulled manually) |
| `--no-restart` | Sync venv + systemd only; do not restart services |
| `--skip-backup` | Skip the pre-update backup (for quick dev iterations) |
| `--remote URL` | Override git remote (default: `https://github.com/oib/AITBC.git`) |
| `-h`, `--help` | Print help and exit |

### Combinations

```bash
# You already pulled manually and just want venv + systemd synced
sudo /opt/aitbc/scripts/deployment/update.sh --no-pull

# Pull and sync, but don't restart (e.g. during a maintenance window)
sudo /opt/aitbc/scripts/deployment/update.sh --no-restart

# Quick dev iteration — skip backup and pull, just sync venv + restart
sudo /opt/aitbc/scripts/deployment/update.sh --no-pull --skip-backup
```

## What the script does (step by step)

### Step 0: Pre-update backup

Triggers `aitbc-backup.service` (oneshot) via `systemctl start` and waits
for it to complete (up to 5 minutes). The backup includes:

- PostgreSQL databases (`pg_dump`)
- Blockchain SQLite databases (`.dump`)
- Keystore and service configs
- Redis RDB snapshot

If the backup fails, the script **warns but continues** — a flaky backup
shouldn't block an update. You can inspect failures with:

```bash
journalctl -u aitbc-backup.service -n 50 --no-pager
```

Skip with `--skip-backup` if you have a recent backup already.

### Step 1: git pull

Fetches and merges from the public GitHub repo
(`https://github.com/oib/AITBC.git`, branch `main`).

- **Local changes detected?** The script stashes them with a timestamped
  message, pulls, then pops the stash. If the pop conflicts, the stash is
  preserved (`git stash list`) and you resolve manually.
- **Non-fast-forward?** The script aborts and tells you to resolve
  manually with `git pull --rebase <remote> main`.
- **No changes?** Prints "Already up to date" and skips venv/systemd
  work if `--no-restart` is also set.

To pull from a different remote (e.g. a private mirror), use:

```bash
sudo /opt/aitbc/scripts/deployment/update.sh --remote http://gitea.example.com/oib/aitbc.git
# or via env var:
sudo AITBC_GIT_REMOTE=http://gitea.example.com/oib/aitbc.git /opt/aitbc/scripts/deployment/update.sh
```

### Step 2: Sync Python venv

Reinstalls dependencies into `/opt/aitbc/venv`:

1. Upgrades `pip`
2. Runs `install-profiles.sh <profile>` where `<profile>` is detected
   from `/etc/aitbc/node.env` (e.g. `follower-shop-gpu`, `hub`,
   `follower-customer`)
3. Falls back to `pip install -r requirements.txt` +
   `pip install -r cli/requirements-cli.txt` if `install-profiles.sh`
   fails or is missing
4. Reinstalls the `aitbc` CLI via `pip install -e cli/`

### Step 3: Relink systemd unit files

Runs `scripts/utils/link-systemd.sh`, which:

- Removes stale `aitbc-*` symlinks from `/etc/systemd/system/`
- Creates fresh symlinks from the repo's `apps/*/aitbc-*.service` and
  `*.timer` files
- Filters by node role (e.g. a `follower:shop:gpu` node only gets
  base + follower + shop services, not hub-only ones)

Then runs `systemctl daemon-reload` so systemd picks up any changed unit
files.

### Step 4: Enable services for this role

Ensures every `aitbc-*.service` and `aitbc-*.timer` currently linked is
enabled (so they survive reboots). Newly added services for your role
get enabled; services no longer in the repo get unlinked by
`link-systemd.sh` and thus won't be enabled.

### Step 5: Restart all running aitbc services

Lists currently-running `aitbc-*` services and restarts each one. After
restart, waits 10 seconds for services to settle, then reports
`Services active: N/M`.

Failed restarts are reported with a hint to check logs:

```bash
journalctl -u <service-name> -n 50 --no-pager
```

Skip with `--no-restart` if you want to restart services manually or
during a maintenance window.

### Step 6: Health check

Runs `scripts/monitoring/health_check.sh`, which checks:

- Service status (`systemctl is-active`)
- HTTP health endpoints for services that expose them
- CPU / memory / disk usage

The health check is advisory — failures are reported as warnings, not
fatal. Investigate any `ERROR:` lines in the output.

### Step 7: Summary

Prints:

- Node role (e.g. `follower:shop:gpu`)
- Current repo HEAD
- Venv path
- Whether services were restarted
- Manual follow-up reminders (see below)

## Manual follow-ups after an update

`update.sh` intentionally does **not** do these automatically — they
require DB credentials, can be destructive, or need human judgement.

### Database migrations (alembic)

If the update included schema changes, run alembic manually:

```bash
cd /opt/aitbc/apps/blockchain-node && alembic upgrade head
```

Other apps with migrations:

```bash
cd /opt/aitbc/apps/coordinator-api && ls migrations/
cd /opt/aitbc/apps/governance && alembic upgrade head
```

### Config template diff

New features may require new env vars. Diff your live config against the
updated templates:

```bash
diff /etc/aitbc/node.env /opt/aitbc/examples/node.env.open-island
diff /etc/aitbc/blockchain.env /opt/aitbc/examples/blockchain.env.example
```

Add any new required vars to `/etc/aitbc/*.env` and restart the affected
service.

### Restart services manually (if you used `--no-restart`)

```bash
# Restart all aitbc services
sudo systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc \
    aitbc-wallet aitbc-coordinator-api aitbc-gpu aitbc-miner \
    aitbc-monitoring aitbc-blockchain-explorer

# Or just the ones affected by the update
sudo systemctl restart aitbc-wallet aitbc-coordinator-api
```

### Verify the update

```bash
# Check service status
systemctl list-units --type=service --state=running | grep aitbc

# Check health endpoints
curl -s http://localhost:8203/health | jq .
curl -s http://localhost:8006/health | jq .

# Check the blockchain node synced to the latest block
aitbc blockchain status

# Check the CLI version
aitbc --version
```

## Rolling back

If the update breaks something, restore from the pre-update backup:

```bash
# List recent backups
ls -lt /var/backups/aitbc/ | head

# Restore PostgreSQL (example: governance DB)
BACKUP_DIR=/var/backups/aitbc/20260622_133800
gunzip -c "$BACKUP_DIR/governance_postgres.sql.gz" \
    | PGPASSWORD=$(cat /etc/aitbc/credentials/postgres_aitbc_governance_password) \
      psql -U aitbc_governance -h localhost aitbc_governance

# Restore blockchain SQLite DB
gunzip -c "$BACKUP_DIR/chain_blockchain.db.gz" > /var/lib/aitbc/data/blockchain.db

# Roll back code
cd /opt/aitbc
git reset --hard <previous-commit-sha>
sudo systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc aitbc-wallet
```

See `scripts/maintenance/restore_postgresql.sh` and
`scripts/maintenance/restore_ledger.sh` for helper scripts.

## `setup.sh` vs `update.sh`

| | `setup.sh` | `update.sh` |
|---|---|---|
| **Purpose** | First-time install | Apply updates to an existing node |
| **Creates DBs** | Yes | No |
| **Creates credentials** | Yes | No |
| **Creates node identity** | Yes | No |
| **Pulls code** | Yes (clones) | Yes (pulls) |
| **Syncs venv** | Yes | Yes |
| **Relinks systemd** | Yes | Yes |
| **Backs up first** | No | Yes |
| **Restarts services** | Yes (starts) | Yes (restarts) |
| **Idempotent?** | Mostly (preserves existing) | Yes |

**Forwarding:** If you run `setup.sh` on a node that's already installed
(detected via `/etc/aitbc/node.env` + `/opt/aitbc/venv`), it
automatically forwards to `update.sh`. Use `setup.sh --force` to bypass
the forward and re-run the full install (e.g. to repair a broken node).

## Troubleshooting

### `git fetch failed (network issue or bad remote)`

The script fetches from `https://github.com/oib/AITBC.git` by default. If
GitHub is unreachable or you want to use a different remote:

```bash
sudo /opt/aitbc/scripts/deployment/update.sh --remote http://your-mirror/oib/aitbc.git
```

### `git merge --ff-only failed (non-fast-forward or local commits diverged)`

You have local commits that diverged from the remote `main`. Resolve manually:

```bash
cd /opt/aitbc
git fetch https://github.com/oib/AITBC.git main
git rebase FETCH_HEAD
# or, if you want to keep your commits on top:
git merge FETCH_HEAD
```

Then re-run `update.sh --no-pull`.

### `Failed to activate venv` / `venv broken`

The venv is corrupted. Recreate it:

```bash
sudo rm -rf /opt/aitbc/venv
sudo python3 -m venv /opt/aitbc/venv
sudo /opt/aitbc/scripts/deployment/update.sh --no-pull
```

### `aitbc-backup.service did not report success`

The pre-update backup failed. Check why:

```bash
journalctl -u aitbc-backup.service -n 50 --no-pager
```

Common causes: out of disk space in `/var/backups/aitbc`, missing
PostgreSQL credentials, or `pg_dump` version mismatch. The update
proceeds anyway, but you should fix the backup before the next update.

### Services won't start after restart

Check the logs for the failing service:

```bash
journalctl -u aitbc-blockchain-node -n 100 --no-pager
journalctl -u aitbc-wallet -n 100 --no-pager
```

Common causes after an update:

- **Missing env var** — a new feature requires a var you don't have in
  `/etc/aitbc/<service>.env`. Diff against `examples/` templates.
- **DB schema mismatch** — you need to run `alembic upgrade head`
- **Python import error** — a new dependency wasn't installed. Re-run
  `update.sh --no-pull` or manually `pip install -r requirements.txt`
  inside the venv.

### `Health check reported issues`

The health check has a hardcoded list of services it checks, including
some hub-only services. On a follower/shop node, warnings about
`aitbc-marketplace`, `aitbc-agent-coordinator`, or `aitbc-exchange-api`
being inactive are **expected** — those services don't run on your role.

Real failures to investigate:

- Any service in your role that's reported `inactive`
- Any health endpoint returning non-200
- Disk usage above 90%

## See also

- [SETUP.md](./SETUP.md) — first-time installation guide
- [open-island.md](./open-island.md) — joining an open island hub
- [free-ait.md](./free-ait.md) — requesting free AIT tokens
- `scripts/deployment/update.sh --help` — built-in help
- `scripts/maintenance/aitbc-backup.sh` — backup script (triggered by
  `aitbc-backup.service`)
- `scripts/monitoring/health_check.sh` — health check script
