#!/bin/bash
# Manage self-serve join keys issued by POST /rpc/join (peer_keys.db).
#
# Issued keys are bound to a single node_id; only their hash is stored.
# Fleet peer keys in BLOCKCHAIN_RPC_API_KEY_PEERS are separate and are not
# managed here.
#
# Usage (on the hub, as root):
#   manage-peer-keys.sh list [--all]      # active keys (or incl. revoked)
#   manage-peer-keys.sh show <node_id>    # record for one node
#   manage-peer-keys.sh revoke <node_id>  # revoke so the node can re-join

set -euo pipefail

DB="${PEER_KEYS_DB:-/var/lib/aitbc/data/peer_keys.db}"
CMD="${1:-list}"
NODE="${2:-}"

[ -f "$DB" ] || { echo "No peer key store at $DB — no keys issued yet." >&2; exit 1; }

run_sql() { sudo -u aitbc sqlite3 "$DB" "$1"; }

if [ -n "$NODE" ] && ! [[ "$NODE" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{2,63}$ ]]; then
    echo "Invalid node_id" >&2
    exit 1
fi

case "$CMD" in
    list)
        if [ "${2:-}" = "--all" ]; then
            run_sql "SELECT node_id, issued_ip, datetime(created_at,'unixepoch'), COALESCE(contact,''), CASE WHEN revoked_at IS NULL THEN 'active' ELSE 'revoked' END FROM peer_keys ORDER BY created_at;"
        else
            run_sql "SELECT node_id, issued_ip, datetime(created_at,'unixepoch'), COALESCE(contact,'') FROM peer_keys WHERE revoked_at IS NULL ORDER BY created_at;"
        fi
        ;;
    show)
        [ -n "$NODE" ] || { echo "usage: $0 show <node_id>" >&2; exit 1; }
        run_sql "SELECT node_id, issued_ip, datetime(created_at,'unixepoch'), COALESCE(contact,''), CASE WHEN revoked_at IS NULL THEN 'active' ELSE 'revoked '||datetime(revoked_at,'unixepoch') END FROM peer_keys WHERE node_id = '$NODE' ORDER BY created_at;"
        ;;
    revoke)
        [ -n "$NODE" ] || { echo "usage: $0 revoke <node_id>" >&2; exit 1; }
        run_sql "UPDATE peer_keys SET revoked_at = strftime('%s','now') WHERE node_id = '$NODE' AND revoked_at IS NULL;"
        echo "Revoked active key for $NODE (if any). The node may now re-join via POST /rpc/join."
        ;;
    *)
        echo "usage: $0 [list [--all] | show <node_id> | revoke <node_id>]" >&2
        exit 1
        ;;
esac
