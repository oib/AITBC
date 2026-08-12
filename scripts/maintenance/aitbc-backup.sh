#!/bin/bash
# AITBC Production Backup Script
# Backs up: PostgreSQL, blockchain SQLite DB, keystore, and service configs
# Schedule: Daily via systemd timer
# Retention: 30 days

set -euo pipefail

BACKUP_BASE="/var/backups/aitbc"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"
RETENTION_DAYS=30
LOG_TAG="aitbc-backup"

# Log to journal with proper priority levels (info/warning/err).
# When running interactively (TTY), also echo to console.
_log() { local pri="$1" msg="$2"; systemd-cat -t "$LOG_TAG" -p "$pri" <<< "$msg"; [[ -t 1 ]] && echo "$msg" || true; }
log()  { _log info    "$1"; }
warn() { _log warning "WARN: $1"; }
error(){ _log err     "ERROR: $1" >&2; }

log "Starting AITBC backup to ${BACKUP_DIR}"
mkdir -p "${BACKUP_DIR}"

# ── PostgreSQL ────────────────────────────────────────────────────────────────
# Back up all AITBC PostgreSQL databases, not just governance.
PG_DBS=(
    "aitbc_governance"
    "aitbc_marketplace"
    "aitbc_trading"
    "aitbc_user"
    "aitbc_mempool"
    "aitbc_gpu"
)

for pg_db in "${PG_DBS[@]}"; do
    # Map database name to service/env name for credential discovery
    pg_service="aitbc-${pg_db#aitbc_}"
    pg_creds="/etc/aitbc/credentials/postgres_${pg_db}_password"
    pg_env="/etc/aitbc/${pg_service}.env"
    pg_pw=""

    if [ -f "$pg_creds" ]; then
        pg_pw=$(cat "$pg_creds")
    elif [ -f "$pg_env" ]; then
        pg_pw=$(grep "^DB_PASS=" "$pg_env" 2>/dev/null | cut -d= -f2- || true)
    fi

    pg_user="${pg_db}"
    if [ -f "$pg_env" ]; then
        pg_user_env=$(grep "^DB_USER=" "$pg_env" 2>/dev/null | cut -d= -f2- || true)
        [ -n "$pg_user_env" ] && pg_user="$pg_user_env"
    fi

    log "Backing up PostgreSQL ${pg_db}..."
    if [ -z "$pg_pw" ]; then
        warn "PostgreSQL backup SKIPPED for ${pg_db}: no password found"
    else
        if PGPASSWORD="$pg_pw" pg_dump -U "$pg_user" -h localhost "$pg_db" \
            | gzip > "${BACKUP_DIR}/postgres_${pg_db}.sql.gz"; then
            log "PostgreSQL backup: OK for ${pg_db} ($(du -sh "${BACKUP_DIR}/postgres_${pg_db}.sql.gz" | cut -f1))"
        else
            error "PostgreSQL backup FAILED for ${pg_db}"
        fi
    fi
done

# ── Blockchain SQLite DB ──────────────────────────────────────────────────────
CHAIN_DB_DIR="/var/lib/aitbc/data"
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
KEYSTORE_DIR="/var/lib/aitbc/keystore"
if [ -d "$KEYSTORE_DIR" ]; then
    log "Backing up keystore..."
    tar czf "${BACKUP_DIR}/keystore.tar.gz" -C "$(dirname "$KEYSTORE_DIR")" "$(basename "$KEYSTORE_DIR")" \
        && log "Keystore backup: OK ($(du -sh "${BACKUP_DIR}/keystore.tar.gz" | cut -f1))" \
        || error "Keystore backup FAILED"
fi

# ── Wallet files ──────────────────────────────────────────────────────────────
WALLETS_DIR="/var/lib/aitbc/wallets"
if [ -d "$WALLETS_DIR" ]; then
    log "Backing up wallet files..."
    tar czf "${BACKUP_DIR}/wallets.tar.gz" -C "$(dirname "$WALLETS_DIR")" "$(basename "$WALLETS_DIR")" \
        && log "Wallets backup: OK ($(du -sh "${BACKUP_DIR}/wallets.tar.gz" | cut -f1))" \
        || error "Wallets backup FAILED"
fi

# ── Service Configuration ─────────────────────────────────────────────────────
log "Backing up service configurations..."
tar czf "${BACKUP_DIR}/etc-aitbc.tar.gz" /etc/aitbc/ 2>/dev/null \
    && log "/etc/aitbc: OK" || error "/etc/aitbc backup FAILED"

tar czf "${BACKUP_DIR}/prometheus-config.tar.gz" /etc/prometheus/ 2>/dev/null \
    && log "/etc/prometheus: OK" || error "Prometheus config backup FAILED"

# ── Redis RDB Snapshot ────────────────────────────────────────────────────────
log "Triggering Redis snapshot..."
redis-cli BGSAVE > /dev/null 2>&1 && sleep 2
REDIS_RDB=$(redis-cli CONFIG GET dir 2>/dev/null | tail -1)
REDIS_FILE=$(redis-cli CONFIG GET dbfilename 2>/dev/null | tail -1)
if [ -f "${REDIS_RDB}/${REDIS_FILE}" ]; then
    cp "${REDIS_RDB}/${REDIS_FILE}" "${BACKUP_DIR}/redis.rdb" \
        && log "Redis RDB: OK ($(du -sh "${BACKUP_DIR}/redis.rdb" | cut -f1))" \
        || error "Redis RDB copy FAILED"
else
    warn "Redis RDB not found, skipping"
fi

# ── Key audit ─────────────────────────────────────────────────────────────────
log "Running key/address audit..."
if PYTHONPATH="/opt/aitbc" /opt/aitbc/venv/bin/python /opt/aitbc/scripts/ops/key-audit.py --report "${BACKUP_DIR}/key-audit.json"; then
    if /opt/aitbc/venv/bin/python -c "import json,sys; sys.exit(0 if json.load(open('${BACKUP_DIR}/key-audit.json')).get('ok') else 1)"; then
        log "Key audit: OK (see ${BACKUP_DIR}/key-audit.json)"
    else
        warn "Key audit: mismatches detected (see ${BACKUP_DIR}/key-audit.json)"
    fi
else
    error "Key audit: script failed"
fi

# ── Finalize ──────────────────────────────────────────────────────────────────
TOTAL=$(du -sh "${BACKUP_DIR}" | cut -f1)
log "Backup complete: ${BACKUP_DIR} (total: ${TOTAL})"

# ── Prune old backups ─────────────────────────────────────────────────────────
log "Pruning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_BASE}" -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} + 2>/dev/null \
    && log "Prune complete" || true

KEPT=$(find "${BACKUP_BASE}" -maxdepth 1 -type d | grep -c "^${BACKUP_BASE}/[0-9]" || echo 0)
log "Retained backup snapshots: ${KEPT}"
