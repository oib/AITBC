#!/bin/bash
# AITBC Production Backup Script
# Backs up: PostgreSQL, blockchain SQLite DB, keystore, and service configs
# Schedule: Daily via systemd timer
# Retention: 30 days

set -euo pipefail

BACKUP_BASE="${BACKUP_BASE:-/var/backups/aitbc}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
# Minimum number of good snapshots pruning must keep. Good = the directory
# holds a nonzero chain_*_chain.db.gz that passes gzip -t (integrity check,
# on by default; BACKUP_GOOD_REQUIRE_GZIP_TEST=no restores the size-only rule).
BACKUP_KEEP_MIN_GOOD="${BACKUP_KEEP_MIN_GOOD:-7}"
BACKUP_GOOD_REQUIRE_GZIP_TEST="${BACKUP_GOOD_REQUIRE_GZIP_TEST:-yes}"
# BACKUP_PRUNE_DRYRUN=yes: run the full prune decision loop but log
# "would remove" instead of deleting. First deploy should run this once so the
# operator sees the one-off deletion list before it happens for real.
BACKUP_PRUNE_DRYRUN="${BACKUP_PRUNE_DRYRUN:-}"
LOG_TAG="aitbc-backup"
# Exit status of the run; legs that leave no usable snapshot set it nonzero.
_BACKUP_RC=0

# Use the active project Python if available, falling back to whatever is on PATH.
# This keeps the backup compatible with both Poetry `.venv` and `venv` layouts.
PYTHON="${PYTHON:-/opt/aitbc/venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

# Optional encrypted off-site backup configuration:
#   BACKUP_GPG_RECIPIENT      GPG key ID/recipient used to encrypt key material.
#   BACKUP_OFFSITE_SCRIPT     Operator-provided script that uploads $BACKUP_DIR.
#   BACKUP_SHRED_PLAINTEXT    Set to "yes" to remove unencrypted key archives after
#                             a successful off-site upload (only when GPG recipient
#                             and off-site script are set).
BACKUP_GPG_RECIPIENT="${BACKUP_GPG_RECIPIENT:-}"
BACKUP_OFFSITE_SCRIPT="${BACKUP_OFFSITE_SCRIPT:-}"
BACKUP_SHRED_PLAINTEXT="${BACKUP_SHRED_PLAINTEXT:-}"
# Space-separated list of backup artifacts to encrypt for the off-site copy.
# The default is the long-standing list; extending it to wallets-legacy_*,
# chain_keystore.db.gz or chain_peer_keys.db.gz is an operator decision —
# see the off-site allow-list discussion in the restore runbook (§8).
BACKUP_GPG_ARTIFACTS="${BACKUP_GPG_ARTIFACTS:-keystore.tar.gz wallets.tar.gz etc-aitbc.tar.gz}"

# Log to journal with proper priority levels (info/warning/err).
# When running interactively (TTY), also echo to console.
_log() { local pri="$1" msg="$2"; systemd-cat -t "$LOG_TAG" -p "$pri" <<< "$msg"; [[ -t 1 ]] && echo "$msg" || true; }
log()  { _log info    "$1"; }
warn() { _log warning "WARN: $1"; }
error(){ _log err     "ERROR: $1" >&2; }

log "Starting AITBC backup to ${BACKUP_DIR}"
mkdir -p "${BACKUP_DIR}"

# ── PostgreSQL ────────────────────────────────────────────────────────────────
# Back up AITBC PostgreSQL databases that actually exist.
# aitbc_user is a role, not a database; aitbc_poolhub is added for the pool-hub service.
PG_DBS=(
    "aitbc_governance"
    "aitbc_market"
    "aitbc_trading"
    "aitbc_mempool"
    "aitbc_gpu"
    "aitbc_poolhub"
)

for pg_db in "${PG_DBS[@]}"; do
    # Map database name to service/env name for credential discovery
    pg_service="aitbc-${pg_db#aitbc_}"
    pg_creds="/etc/aitbc/credentials/postgres_${pg_db}_password"
    pg_env="/etc/aitbc/${pg_service}.env"
    pg_pw=""
    pg_user="${pg_db}"

    # aitbc_poolhub is managed by aitbc-pool-hub and uses the poolhub user
    if [ "$pg_db" = "aitbc_poolhub" ]; then
        pg_service="aitbc-pool-hub"
        pg_env="/etc/aitbc/${pg_service}.env"
        pg_user="poolhub"
    fi

    # The mempool has no service or env file of its own -- it belongs to
    # blockchain-node, which selects its backend via MEMPOOL_DB_URL. That URL is
    # sqlite on every host in this fleet, so the aitbc_mempool database exists
    # (setup_postgresql_databases.sh creates it unconditionally) but nothing ever
    # writes to it. Dumping it is pointless, and the stale role password made the
    # attempt fail nightly. Skip unless the node is actually pointed at postgres.
    if [ "$pg_db" = "aitbc_mempool" ]; then
        pg_env="/etc/aitbc/blockchain.env"
        mempool_url=$(grep "^MEMPOOL_DB_URL=" "$pg_env" 2>/dev/null | cut -d= -f2- || true)
        case "$mempool_url" in
            postgres*) ;;
            *)
                log "PostgreSQL backup skipped for ${pg_db}: MEMPOOL_DB_URL is not postgres, so this database is unused"
                continue
                ;;
        esac
    fi

    if [ -f "$pg_creds" ]; then
        pg_pw=$(cat "$pg_creds")
    elif [ -f "$pg_env" ]; then
        pg_pw=$(grep "^DB_PASS=" "$pg_env" 2>/dev/null | cut -d= -f2- || true)
        # aitbc-pool-hub stores its DSN in POOLHUB_POSTGRES_DSN
        if [ -z "$pg_pw" ]; then
            pg_pw=$(grep "^POOLHUB_POSTGRES_DSN=" "$pg_env" 2>/dev/null | cut -d= -f2- | sed -E 's|^[^/]+://[^:]*:([^@]+)@.*$|\1|' || true)
        fi
        # The mempool DSN carries its own credentials; blockchain.env has no DB_PASS.
        if [ -z "$pg_pw" ] && [ "$pg_db" = "aitbc_mempool" ]; then
            pg_pw=$(grep "^MEMPOOL_DB_URL=" "$pg_env" 2>/dev/null | cut -d= -f2- | sed -E 's|^[^/]+://[^:]*:([^@]+)@.*$|\1|' || true)
        fi
    fi

    if [ -f "$pg_env" ]; then
        pg_user_env=$(grep "^DB_USER=" "$pg_env" 2>/dev/null | cut -d= -f2- || true)
        [ -n "$pg_user_env" ] && pg_user="$pg_user_env"
    fi

    # Only back up databases that actually exist; this removes DUMP_FAILED
    # artifacts and tiny backup files for unused or corrupt PostgreSQL databases.
    if ! sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${pg_db}'" 2>/dev/null | grep -q 1; then
        warn "PostgreSQL backup SKIPPED for ${pg_db}: database does not exist"
        continue
    fi

    log "Backing up PostgreSQL ${pg_db}..."
    if [ -z "$pg_pw" ]; then
        warn "PostgreSQL backup SKIPPED for ${pg_db}: no password found"
    else
        if PGPASSWORD="$pg_pw" pg_dump -U "$pg_user" -h localhost "$pg_db" \
            | gzip > "${BACKUP_DIR}/postgres_${pg_db}.sql.gz"; then
            chmod 600 "${BACKUP_DIR}/postgres_${pg_db}.sql.gz"
            log "PostgreSQL backup: OK for ${pg_db} ($(du -sh "${BACKUP_DIR}/postgres_${pg_db}.sql.gz" | cut -f1))"
        else
            # pipefail makes the pipeline report pg_dump's failure, but gzip has
            # already created the output file -- an empty 20-byte archive that
            # looks like a backup in a directory listing. Remove it so a failed
            # dump leaves no artifact to mistake for one.
            rm -f "${BACKUP_DIR}/postgres_${pg_db}.sql.gz"
            error "PostgreSQL backup FAILED for ${pg_db}"
        fi
    fi
done

# ── Blockchain SQLite DB ──────────────────────────────────────────────────────
CHAIN_DB_DIR="${CHAIN_DB_DIR:-/var/lib/aitbc/data}"
if [ -d "$CHAIN_DB_DIR" ]; then
    log "Backing up blockchain SQLite databases..."
    find "$CHAIN_DB_DIR" -name "*.db" | while read -r dbfile; do
        rel=$(echo "$dbfile" | sed "s|${CHAIN_DB_DIR}/||")
        dest="${BACKUP_DIR}/chain_$(echo "$rel" | tr '/' '_').gz"
        # Use SQLite online backup via .dump to get consistent snapshot
        sqlite3 "$dbfile" ".dump" 2>/dev/null | gzip > "$dest" \
            && log "SQLite $(basename "$dbfile"): OK" \
            || error "SQLite $(basename "$dbfile") FAILED"
    done
else
    warn "Chain DB dir not found at ${CHAIN_DB_DIR}, skipping"
fi

# ── Keystore ──────────────────────────────────────────────────────────────────
KEYSTORE_DIR="${KEYSTORE_DIR:-/var/lib/aitbc/keystore}"
if [ -d "$KEYSTORE_DIR" ]; then
    log "Backing up keystore..."
    tar czf "${BACKUP_DIR}/keystore.tar.gz" -C "$(dirname "$KEYSTORE_DIR")" "$(basename "$KEYSTORE_DIR")" \
        && log "Keystore backup: OK ($(du -sh "${BACKUP_DIR}/keystore.tar.gz" | cut -f1))" \
        || error "Keystore backup FAILED"
fi

# ── Wallet files ──────────────────────────────────────────────────────────────
WALLETS_DIR="${WALLETS_DIR:-/var/lib/aitbc/wallets}"
if [ -d "$WALLETS_DIR" ]; then
    log "Backing up wallet files..."
    tar czf "${BACKUP_DIR}/wallets.tar.gz" -C "$(dirname "$WALLETS_DIR")" "$(basename "$WALLETS_DIR")" \
        && log "Wallets backup: OK ($(du -sh "${BACKUP_DIR}/wallets.tar.gz" | cut -f1))" \
        || error "Wallets backup FAILED"
fi

# ── Legacy wallet directories (pre-standard) ──────────────────────────────────
# Plain-text file wallets may still live under ~/.aitbc/wallets on nodes that
# have not yet migrated to /var/lib/aitbc/wallets. Back them up until the
# migration is complete so private keys are not lost. Backup artifacts are
# restricted to root:aitbc-services.
# Space-separated in env form; defaults are the two historical locations.
read -ra LEGACY_WALLET_DIRS <<< "${LEGACY_WALLET_DIRS:-/home/aitbc/.aitbc/wallets /root/.aitbc/wallets}"
for LEGACY_WALLET_DIR in "${LEGACY_WALLET_DIRS[@]}"; do
    if [ -d "$LEGACY_WALLET_DIR" ]; then
        log "Backing up legacy wallet directory ${LEGACY_WALLET_DIR}..."
        _legacy_parent=$(dirname "$LEGACY_WALLET_DIR")
        _legacy_name=$(basename "$LEGACY_WALLET_DIR")
        _legacy_suffix=$(echo "$LEGACY_WALLET_DIR" | tr '/' '_')
        tar czf "${BACKUP_DIR}/wallets-legacy${_legacy_suffix}.tar.gz" -C "${_legacy_parent}" "${_legacy_name}" \
            && log "Legacy wallets ${LEGACY_WALLET_DIR}: OK" \
            || error "Legacy wallets ${LEGACY_WALLET_DIR} backup FAILED"
    fi
done

# ── Service Configuration ─────────────────────────────────────────────────────
ETC_AITBC_DIR="${ETC_AITBC_DIR:-/etc/aitbc}"
ETC_PROMETHEUS_DIR="${ETC_PROMETHEUS_DIR:-/etc/prometheus}"
log "Backing up service configurations..."
tar czf "${BACKUP_DIR}/etc-aitbc.tar.gz" "${ETC_AITBC_DIR}" 2>/dev/null \
    && log "/etc/aitbc: OK" || error "/etc/aitbc backup FAILED"

if [ -d "${ETC_PROMETHEUS_DIR}" ]; then
    tar czf "${BACKUP_DIR}/prometheus-config.tar.gz" "${ETC_PROMETHEUS_DIR}" 2>/dev/null \
        && log "/etc/prometheus: OK" || error "Prometheus config backup FAILED"
else
    warn "${ETC_PROMETHEUS_DIR} not found, skipping"
fi

# ── Redis RDB Snapshot ────────────────────────────────────────────────────────
# REDISCLI_AUTH comes from the backup env file (aitbc-backup.env). redis-cli
# reads it natively from the environment, so the password never appears on the
# command line or in process arguments. Exported only when set.
if [ -n "${REDISCLI_AUTH:-}" ]; then
    export REDISCLI_AUTH
fi
if command -v redis-cli >/dev/null 2>&1; then
    log "Triggering Redis snapshot..."
    _redis_rc=0
    _redis_out="$(redis-cli BGSAVE 2>&1)" || _redis_rc=$?
    # Only the acknowledged reply passes; NOAUTH/ERR/any other text is a
    # failure, and a failed BGSAVE means no fresh snapshot -- do not go on to
    # copy a possibly stale dump file afterwards.
    if [ "$_redis_rc" -eq 0 ] && [ "$_redis_out" = "Background saving started" ]; then
        log "Redis BGSAVE: ${_redis_out}"
        sleep 2
        REDIS_RDB=$(redis-cli CONFIG GET dir 2>/dev/null | tail -1)
        REDIS_FILE=$(redis-cli CONFIG GET dbfilename 2>/dev/null | tail -1)
        if [ -f "${REDIS_RDB}/${REDIS_FILE}" ]; then
            if cp "${REDIS_RDB}/${REDIS_FILE}" "${BACKUP_DIR}/redis.rdb"; then
                log "Redis RDB: OK ($(du -sh "${BACKUP_DIR}/redis.rdb" | cut -f1))"
            else
                error "Redis RDB copy FAILED"
                _BACKUP_RC=1
            fi
        else
            error "Redis RDB not found at ${REDIS_RDB}/${REDIS_FILE} after BGSAVE reported started"
            _BACKUP_RC=1
        fi
    else
        error "Redis BGSAVE FAILED (rc=${_redis_rc}): ${_redis_out:-no output}"
        _BACKUP_RC=1
    fi
else
    warn "redis-cli not installed, skipping Redis snapshot"
fi

# ── Key audit ─────────────────────────────────────────────────────────────────
log "Running key/address audit..."
if PYTHONPATH="/opt/aitbc" "$PYTHON" /opt/aitbc/scripts/ops/key-audit.py --report "${BACKUP_DIR}/key-audit.json"; then
    if "$PYTHON" -c "import json,sys; sys.exit(0 if json.load(open('${BACKUP_DIR}/key-audit.json')).get('ok') else 1)"; then
        log "Key audit: OK (see ${BACKUP_DIR}/key-audit.json)"
    else
        warn "Key audit: mismatches detected (see ${BACKUP_DIR}/key-audit.json)"
    fi
else
    error "Key audit: script failed"
fi

# ── Optional encrypted off-site copy of key material ───────────────────────────
# If a GPG recipient and an off-site upload script are configured, create an
# encrypted copy of keystore/wallet artifacts and upload it. The plaintext local
# archives remain in place for quick restore unless BACKUP_SHRED_PLAINTEXT=yes.
_OFFSITE_OK=false
if [ -n "$BACKUP_GPG_RECIPIENT" ]; then
    if command -v gpg >/dev/null 2>&1; then
        # Intentionally unquoted: BACKUP_GPG_ARTIFACTS is a space-separated list.
        for artifact in ${BACKUP_GPG_ARTIFACTS}; do
            src="${BACKUP_DIR}/${artifact}"
            if [ -f "$src" ]; then
                log "Encrypting ${artifact} for off-site backup..."
                if gpg --batch --yes --trust-model always \
                       -r "$BACKUP_GPG_RECIPIENT" \
                       -o "${src}.gpg" --encrypt "$src"; then
                    chmod 600 "${src}.gpg"
                    log "Encrypted ${artifact}: OK"
                else
                    error "Encryption FAILED for ${artifact}"
                fi
            fi
        done
    else
        warn "BACKUP_GPG_RECIPIENT set but gpg not installed; skipping encryption"
    fi
fi

if [ -n "$BACKUP_OFFSITE_SCRIPT" ]; then
    if [ -x "$BACKUP_OFFSITE_SCRIPT" ]; then
        log "Uploading backup to off-site destination via ${BACKUP_OFFSITE_SCRIPT}..."
        if "$BACKUP_OFFSITE_SCRIPT" "$BACKUP_DIR"; then
            log "Off-site backup: OK"
            _OFFSITE_OK=true
        else
            error "Off-site backup FAILED"
        fi
    else
        error "BACKUP_OFFSITE_SCRIPT is not executable: ${BACKUP_OFFSITE_SCRIPT}"
    fi
fi

if [ "$BACKUP_SHRED_PLAINTEXT" = "yes" ] && [ -n "$BACKUP_GPG_RECIPIENT" ] && [ "$_OFFSITE_OK" = true ]; then
    log "Removing plaintext key archives after successful off-site upload..."
    # Deliberately a fixed list, not BACKUP_GPG_ARTIFACTS: shredding covers only
    # the key-material archives; config artifacts stay plaintext for restore.
    for artifact in keystore.tar.gz wallets.tar.gz; do
        [ -f "${BACKUP_DIR}/${artifact}" ] && shred -u "${BACKUP_DIR}/${artifact}" 2>/dev/null || rm -f "${BACKUP_DIR}/${artifact}"
    done
fi

# ── Finalize ──────────────────────────────────────────────────────────────────
TOTAL=$(du -sh "${BACKUP_DIR}" | cut -f1)
log "Backup complete: ${BACKUP_DIR} (total: ${TOTAL})"

# Ensure backup artifacts are not world-readable
find "${BACKUP_DIR}" -type f -exec chmod 600 {} + 2>/dev/null || true
chmod 750 "${BACKUP_DIR}" 2>/dev/null || true

# ── Prune old backups ─────────────────────────────────────────────────────────
# Age is read from the directory NAME (YYYYMMDD_HHMMSS), never mtime — any
# touch resets mtime (a Sep-8 touch preserved Aug-named dirs on hub/node2).
# Names that do not parse are never pruned. At least BACKUP_KEEP_MIN_GOOD good
# snapshots are kept, where good = the dir holds a nonzero chain_*_chain.db.gz.
# Nothing is pruned when this run produced no good snapshot itself: emptying
# the vault during a broken-backup stretch is how the last restorable copy
# gets lost.
_is_good_snapshot() {
    local dir="$1" f
    while IFS= read -r f; do
        if [ "$BACKUP_GOOD_REQUIRE_GZIP_TEST" = "no" ] || gzip -t "$f" 2>/dev/null; then
            return 0
        fi
    done < <(find "$dir" -maxdepth 1 -name 'chain_*_chain.db.gz' -size +0c -print 2>/dev/null)
    return 1
}

if _is_good_snapshot "${BACKUP_DIR}"; then
    _good_kept=0
    for d in "${BACKUP_BASE}"/*/; do
        [ -d "$d" ] || continue
        if _is_good_snapshot "${d%/}"; then
            _good_kept=$((_good_kept + 1))
        fi
    done
    log "Pruning backups older than ${RETENTION_DAYS} days by name-date; ${_good_kept} good snapshot(s), keep-min ${BACKUP_KEEP_MIN_GOOD}"
    _now_epoch=$(date +%s)
    for d in "${BACKUP_BASE}"/*/; do
        [ -d "$d" ] || continue
        d="${d%/}"
        _name="$(basename "$d")"
        [ "$d" = "${BACKUP_DIR}" ] && continue
        if ! [[ "$_name" =~ ^[0-9]{8}_[0-9]{6}$ ]]; then
            warn "Prune: '${_name}' does not match YYYYMMDD_HHMMSS — leaving untouched"
            continue
        fi
        _snap_epoch=$(date -d "${_name:0:4}-${_name:4:2}-${_name:6:2} ${_name:9:2}:${_name:11:2}:${_name:13:2}" +%s 2>/dev/null) || {
            warn "Prune: '${_name}' failed date parse — leaving untouched"
            continue
        }
        _age_days=$(( (_now_epoch - _snap_epoch) / 86400 ))
        [ "$_age_days" -le "$RETENTION_DAYS" ] && continue
        if _is_good_snapshot "$d"; then
            if [ "$_good_kept" -le "$BACKUP_KEEP_MIN_GOOD" ]; then
                warn "Prune: '${_name}' is old but among the last ${_good_kept} good snapshots (min ${BACKUP_KEEP_MIN_GOOD}) — keeping"
                continue
            fi
            _good_kept=$((_good_kept - 1))
        fi
        if [ "$BACKUP_PRUNE_DRYRUN" = "yes" ]; then
            log "Prune: would remove '${_name}' (age ${_age_days}d)"
        else
            log "Prune: removing '${_name}' (age ${_age_days}d)"
            rm -rf "$d"
        fi
    done
    log "Prune complete"
else
    warn "This run produced no good snapshot (no nonzero chain_*_chain.db.gz) — pruning skipped entirely"
fi

KEPT=$(find "${BACKUP_BASE}" -maxdepth 1 -type d | grep -c "^${BACKUP_BASE}/[0-9]" || echo 0)
log "Retained backup snapshots: ${KEPT}"

exit "${_BACKUP_RC}"
