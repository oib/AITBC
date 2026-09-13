#!/bin/bash
# Probe every incus proxy device's TCP listen port for the "wedged forkproxy"
# failure mode seen 2026-09-13: the proxy accepts a fresh connection then FINs
# it ~1ms later without ever dialing the backend, while pre-existing
# connections keep relaying.
#
# Detection: open a fresh TCP connection to the listen port and wait briefly.
#   - bytes arrive            -> healthy (bannered service)
#   - read timeout            -> healthy (server waits for client, e.g. pnet)
#   - EOF/reset before timeout -> suspicious: bounce the device and re-probe
#
# Remediation: `incus config device remove` + `add` respawns forkproxy.
# All device properties are captured via `incus query` and re-applied.
#
# Exit 0 = all devices healthy (or healed), 1 = at least one still failing.

set -euo pipefail

TAG="aitbc-proxy-probe"
PROBE_TIMEOUT=4

log() { logger -t "$TAG" -p "user.$1" -- "$2"; echo "[$1] $2"; }

# Fresh-connect probe; runs in a subshell so exec redirections stay local.
# 0 = conn alive (banner read or silent but open), 1 = refused/EOF/reset.
probe_port() (
    exec 3<>"/dev/tcp/$1/$2" 2>/dev/null || exit 1
    rc=0
    read -r -t "$PROBE_TIMEOUT" -N 1 -u 3 _ 2>/dev/null || rc=$?
    # rc=0: got a byte; rc>128: timed out still-open. Both mean the conn lives.
    [ "$rc" -eq 0 ] || [ "$rc" -gt 128 ]
)

# Return the device's full property map as space-separated key=value args.
device_props() {
    incus query "/1.0/instances/$1" |
        python3 -c 'import json,sys
d = json.load(sys.stdin)
dev = d["devices"].get(sys.argv[2]) or {}
dev.pop("type", None)
print(" ".join(f"{k}={v}" for k, v in dev.items()))' "$1" "$2"
}

bounce_device() {
    local inst=$1 dev=$2 kvs
    kvs=$(device_props "$inst" "$dev")
    if [ -z "$kvs" ]; then
        log err "$inst/$dev cannot bounce: failed to read device props"
        return 1
    fi
    log warning "bouncing $inst/$dev (props: $kvs)"
    incus config device remove "$inst" "$dev" >/dev/null
    # shellcheck disable=SC2086 # kvs intentionally word-splits into key=val args
    incus config device add "$inst" "$dev" proxy $kvs >/dev/null
}

failed=0
seen=0

instances=$(incus list -c n -f csv 2>/dev/null) || true
if [ -z "$instances" ]; then
    log err "incus list returned nothing -- incus unreachable?"
    exit 1
fi

while IFS= read -r inst; do
    [ -n "$inst" ] || continue
    while IFS= read -r dev; do
        [ -n "$dev" ] || continue
        listen=$(incus config device get "$inst" "$dev" listen 2>/dev/null) || continue
        [ -n "$listen" ] || continue
        proto=${listen%%:*}
        [ "$proto" = "tcp" ] || continue
        rest=${listen#*:}
        port=${rest##*:}
        host=${rest%:*}
        [ -n "$port" ] || continue
        # nat=true devices have no host listener; dial the configured listen
        # address so the DNAT output chain handles it. Wildcard listeners use
        # loopback.
        nat=$(incus config device get "$inst" "$dev" nat 2>/dev/null || true)
        if [ "$nat" = "true" ]; then
            [ "$host" = "0.0.0.0" ] && continue # unreachable in nat mode
            target=$host
        else
            target=127.0.0.1
        fi
        seen=$((seen + 1))
        if probe_port "$target" "$port" || { sleep 2; probe_port "$target" "$port"; }; then
            log info "$inst/$dev $target:$port OK"
            continue
        fi
        log err "$inst/$dev $target:$port fresh connection dies instantly (wedged proxy or dead backend)"
        if bounce_device "$inst" "$dev" && sleep 1 && probe_port "$target" "$port"; then
            log info "$inst/$dev $target:$port healed after device bounce"
        else
            log err "$inst/$dev $target:$port STILL FAILING after bounce -- backend likely dead, manual check needed"
            failed=$((failed + 1))
        fi
    done < <(incus config device list "$inst" 2>/dev/null)
done <<<"$instances"

if [ "$seen" -eq 0 ]; then
    log warning "no incus proxy devices found"
fi
exit "$failed"
