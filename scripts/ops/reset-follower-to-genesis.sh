#!/bin/bash
# Reset an AITBC follower to the current fork chain database.
#
# This script is intended for the post-fork AITBC chain. The local chain
# database is replaced with a consistent snapshot of the fork database and the
# follower starts from the fork head (which may already contain the genesis and
# several blocks).
#
# The hub does NOT serve a public /agent/chain.db endpoint (V23-58). The
# snapshot must come from an operator-provided source:
#   - a local file:        CHAIN_DB_FILE=/path/to/chain.db
#   - an authenticated URL: CHAIN_DB_URL=https://operator-endpoint/chain.db
#
# Scratch-only usage (reset guard): every path must resolve under
# AITBC_RESET_SCRATCH — DB_DIR, ENV_FILE and CHAIN_DB_FILE all have live
# defaults, so set them explicitly to scratch paths:
#   AITBC_RESET_SCRATCH=/path/to/scratch \
#   DB_DIR=/path/to/scratch/data ENV_FILE=/path/to/scratch/etc/blockchain.env \
#   CHAIN_DB_FILE=/path/to/scratch/chain.db bash reset-follower-to-genesis.sh
# Live units are never stopped or started under the guard; there is no live
# mode — reset-day writes go through scripts/ops/build-genesis.py.

set -euo pipefail

CHAIN_ID="${CHAIN_ID:-ait-localnet}"
# No default download URL: the hub does not publish a public chain.db. Set
# CHAIN_DB_URL to an operator-provided (authenticated) snapshot endpoint, or
# pass a local CHAIN_DB_FILE instead.
CHAIN_DB_URL="${CHAIN_DB_URL:-}"
CHAIN_DB_FILE="${CHAIN_DB_FILE:-}"
DB_DIR="${DB_DIR:-/var/lib/aitbc/data}"
DB="${DB_DIR}/${CHAIN_ID}/chain.db"
UNITS="aitbc-blockchain-node aitbc-blockchain-rpc"
ENV_FILE="${ENV_FILE:-/etc/aitbc/blockchain.env}"

# Scratch-only reset guard: this script replaces a chain DB and edits an env
# file. AITBC_RESET_SCRATCH must name the scratch root and every path this
# script touches must resolve under it. The defaults above are live paths, so
# an unset marker refuses here. There is no live override — reset-day writes
# go through scripts/ops/build-genesis.py.
if [ -z "${AITBC_RESET_SCRATCH:-}" ]; then
    echo "reset-guard: AITBC_RESET_SCRATCH is not set — refusing to run a" >&2
    echo "destructive reset tool outside a declared scratch root." >&2
    exit 1
fi
SCRATCH_ROOT="$(realpath -m "$AITBC_RESET_SCRATCH")"
case "$SCRATCH_ROOT" in
    /var/lib/aitbc|/var/lib/aitbc/*|/etc/aitbc|/etc/aitbc/*|/root|/root/*)
        echo "reset-guard: AITBC_RESET_SCRATCH=$SCRATCH_ROOT is inside a live path" >&2
        exit 1
        ;;
esac
_check_target() {
    _p="$(realpath -m "$1")"
    case "$_p" in
        /var/lib/aitbc|/var/lib/aitbc/*|/etc/aitbc|/etc/aitbc/*|/root|/root/*)
            echo "reset-guard: target $1 resolves inside a live path — refusing" >&2
            exit 1
            ;;
    esac
    case "$_p" in
        "$SCRATCH_ROOT"|"$SCRATCH_ROOT"/*) ;;
        *)
            echo "reset-guard: target $1 resolves to $_p — outside scratch root $SCRATCH_ROOT" >&2
            exit 1
            ;;
    esac
}
_check_target "$DB_DIR"
_check_target "$DB"
_check_target "$ENV_FILE"
[ -n "$CHAIN_DB_FILE" ] && _check_target "$CHAIN_DB_FILE"

# Scratch runs never touch live systemd units — the rehearsal manages its own
# processes; this script only becomes file-ops under the guard.
echo "reset-guard: scratch mode — not stopping or starting systemd units."

# Download the fork chain DB unless a local file is provided.
if [ -z "$CHAIN_DB_FILE" ]; then
    if [ -z "$CHAIN_DB_URL" ]; then
        echo "No chain DB source: set CHAIN_DB_FILE=/path/to/chain.db or" >&2
        echo "CHAIN_DB_URL=<operator-provided snapshot URL>." >&2
        echo "The hub does not serve a public /agent/chain.db (V23-58)." >&2
        exit 1
    fi
    mkdir -p "$SCRATCH_ROOT/download"
    CHAIN_DB_FILE="$SCRATCH_ROOT/download/aitbc-chain-${CHAIN_ID}.db"
    echo "Downloading fork chain DB from $CHAIN_DB_URL"
    if ! curl -fsSL "$CHAIN_DB_URL" -o "$CHAIN_DB_FILE"; then
        echo "Failed to download fork chain DB from $CHAIN_DB_URL" >&2
        exit 1
    fi
fi

[ -f "$CHAIN_DB_FILE" ] || { echo "No chain DB file: $CHAIN_DB_FILE" >&2; exit 1; }

# Preserve the old chain DB in case the operator needs to revert. `sqlite3 .backup` reads through
# the WAL, so the copy is whole even if a service was killed instead of stopped cleanly: on a host
# running with DB_KEEPER_CONNECTION the recent commits can sit in chain.db-wal, and a bare cp of
# chain.db alone would drop them. The raw-copy fallback keeps the WAL files next to the copy.
timestamp=$(date +%Y%m%d-%H%M%S)
if [ -f "$DB" ]; then
    backup="${DB}.pre-reset.${timestamp}"
    if sqlite3 "$DB" ".backup '${backup}'"; then
        chown --reference="$DB" "$backup" || true
        chmod --reference="$DB" "$backup" || true
    else
        echo "sqlite3 .backup failed; keeping a raw copy of the database and its WAL files" >&2
        cp -p "$DB" "$backup"
        for suffix in -wal -shm; do
            if [ -f "${DB}${suffix}" ]; then cp -p "${DB}${suffix}" "${backup}${suffix}"; fi
        done
    fi
    echo "Old chain DB saved to $backup"
    rm -f "$DB"
fi

# Remove stale WAL/SHM files from the previous database, if any.
rm -f "${DB}"-wal "${DB}"-shm

# Install the fork chain DB. Ownership flags only when root — scratch runs may
# execute as an unprivileged user with no aitbc account.
if [ "$(id -u)" = "0" ]; then
    install -D -m 0640 -o aitbc -g aitbc "$CHAIN_DB_FILE" "$DB"
else
    install -D -m 0640 "$CHAIN_DB_FILE" "$DB"
fi
echo "Installed fork chain DB for $CHAIN_ID"

# Ensure the version gate is configured for the v2 fork.
if [ -f "$ENV_FILE" ]; then
    if ! grep -qE '^STATE_TRANSITION_V2_HEIGHT=' "$ENV_FILE"; then
        echo "STATE_TRANSITION_V2_HEIGHT=0" >> "$ENV_FILE"
        echo "Set STATE_TRANSITION_V2_HEIGHT=0 in $ENV_FILE"
    fi
fi

echo "reset-guard: scratch mode — skipping service start (no live units touched)."

echo "Follower reset complete."
