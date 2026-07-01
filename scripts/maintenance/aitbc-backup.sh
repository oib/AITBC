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
# Read password from credentials dir (NOT from blockchain-secrets.env which is published)
GOVERNANCE_PW=""
if [ -f /etc/aitbc/credentials/postgres_aitbc_governance_password ]; then
    GOVERNANCE_PW=$(cat /etc/aitbc/credentials/postgres_aitbc_governance_password)
elif [ -f /etc/aitbc/aitbc-governance.env ]; then
    # Fallback: read DB_PASS from governance env file
    GOVERNANCE_PW=$(grep "^DB_PASS=" /etc/aitbc/aitbc-governance.env 2>/dev/null | cut -d= -f2-)
fi

log "Backing up PostgreSQL aitbc_governance..."
if [ -z "$GOVERNANCE_PW" ]; then
    error "PostgreSQL backup FAILED: no governance password found"
    error "Expected /etc/aitbc/credentials/postgres_aitbc_governance_password or DB_PASS in /etc/aitbc/aitbc-governance.env"
else
    if PGPASSWORD="$GOVERNANCE_PW" pg_dump -U aitbc_governance -h localhost aitbc_governance \
        | gzip > "${BACKUP_DIR}/governance_postgres.sql.gz"; then
        log "PostgreSQL backup: OK ($(du -sh "${BACKUP_DIR}/governance_postgres.sql.gz" | cut -f1))"
    else
        error "PostgreSQL backup FAILED"
    fi
fi

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

# ── Finalize ──────────────────────────────────────────────────────────────────
TOTAL=$(du -sh "${BACKUP_DIR}" | cut -f1)
log "Backup complete: ${BACKUP_DIR} (total: ${TOTAL})"

# ── Prune old backups ─────────────────────────────────────────────────────────
log "Pruning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_BASE}" -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} + 2>/dev/null \
    && log "Prune complete" || true

KEPT=$(find "${BACKUP_BASE}" -maxdepth 1 -type d | grep -c "^${BACKUP_BASE}/[0-9]" || echo 0)
log "Retained backup snapshots: ${KEPT}"
