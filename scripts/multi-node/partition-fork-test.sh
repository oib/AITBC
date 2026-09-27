#!/bin/bash
#
# partition-fork-test.sh — isolate this node so it must propose alone while
# the rest of the validator set keeps building the majority branch, then
# restore connectivity and watch the deterministic fork resolver converge.
#
# Designed to run ON the node being isolated (e.g. node2). Three-layer cut:
#
#   1. blackhole routes (IPv4 + IPv6) for every other validator/tunnel IP
#      — outbound connections die (verified on kernel 6.12: established
#      sockets retransmit after `ip route add blackhole`; a pre-cut
#      `ss -K` sweep on peer dsts removes the ambiguity entirely).
#      10.1.223.1 (the LAN gateway) is deliberately NOT blackholed:
#      router-forwarded inbound ws conns carry attest traffic whose
#      replies must keep flowing — that is how an "isolated" node still
#      satisfies multi_validator_min_attestations.
#
#   2. Redis pub/sub ACL denying `blocks.*` on the default user while
#      `consensus.attest_*` and `transactions*` stay open — this node's own
#      produced block can never reach the broker (publish NOPERM), and
#      inbound block pushes NOPERM on the way in too.
#
#   3. nginx on the node-local vhost: `/rpc/gossip/` stays proxied (ws
#      gossip + attestation transport) while every other `/rpc/` path
#      returns 444 — peer freshness checks and block pulls fail, so the
#      majority produces its OWN block at the contested height instead of
#      importing ours. Backup lives OUTSIDE sites-enabled (a .conf there
#      gets loaded as a duplicate), is validated by `nginx -t` before the
#      reload, and a systemd-run failsafe restores everything even if this
#      script dies.
#
# Trigger arithmetic: the cut arms when the local head H satisfies
# H % <n_validators> == <slot> — with the sorted set
# [0x02B8 hub, 0x241D node1, 0x4364 node2, 0x9Ea1 hub1], node2 owns round 1
# of H+1 when H % 4 == 0 (index (H+1+1)%4 = 2 = 0x4364). The majority's
# first competing block then comes at round 2 — the exact situation where
# round-first fork choice would wrongly prefer the isolated block.
#
# FAILSAFE SAFETY: a previous run's orphaned failsafe once fired mid-window
# and silently restored connectivity (cut6, 2026-09-27 — the resolver still
# decided correctly, but only because both branches had already formed).
# This script uses a FIXED unit name and stops any leftover timer at start
# and on clean restore.
#
# Usage:   sudo ./partition-fork-test.sh [--seconds N] [--slot N] [--nvals N]
# Default: 240s window, slot 0, 4 validators (node2 r1 at H+1).
#
set -euo pipefail

CHAIN="${AITBC_CHAIN_ID:-ait-hub.aitbc.bubuit.net}"
CUT_SECONDS=240
SLOT=0
NVALS=4
FAILSAFE_UNIT="aitbc-partition-failsafe"
NGX=/etc/nginx/sites-enabled/aitbc
BAK=/etc/nginx/aitbc.partition-bak
RPC_PORT=8202

while [ $# -gt 0 ]; do
    case "$1" in
        --seconds) CUT_SECONDS="$2"; shift 2 ;;
        --slot)    SLOT="$2"; shift 2 ;;
        --nvals)   NVALS="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done
if [ "$CUT_SECONDS" -lt 30 ]; then echo "--seconds must be >= 30" >&2; exit 2; fi

ts() { date -u +%T.%3N; }
log() { echo "$(ts) $*"; }

# --- peer address inventory (edit when the fleet changes) -----------------
# hub, hub1 publics + LAN nodes + the dynamic-proxy tunnel endpoint.
PEER_HOSTNAMES="hub.aitbc.bubuit.net hub1.aitbc.bubuit.net"
PEER_IPS="10.1.223.93 10.1.223.40 80.109.18.113"
for hn in $PEER_HOSTNAMES; do
    for ip in $(getent ahostsv4 "$hn" | awk '{print $1}' | sort -u || true); do
        PEER_IPS="$PEER_IPS $ip"
    done
done
PEER_IP6S=""
for hn in $PEER_HOSTNAMES; do
    # skip ::ffff: mapped forms — those traverse the v4 table anyway
    for ip in $(getent ahostsv6 "$hn" | awk '{print $1}' | grep -v '^::ffff:' | sort -u || true); do
        PEER_IP6S="$PEER_IP6S $ip"
    done
done
REDIS_PW=$(grep -hoE "redis://:[^@]+@127.0.0.1" /etc/aitbc/*.env | head -1 | sed "s|redis://:||;s|@.*||" || true)
RCLI="redis-cli -a $REDIS_PW --no-auth-warning"

restore() {
    $RCLI ACL SETUSER default allchannels >/dev/null 2>&1 || true
    for ip in $PEER_IPS; do ip route del blackhole "$ip" 2>/dev/null || true; done
    for ip in ${PEER_IP6S:-}; do ip -6 route del blackhole "$ip" 2>/dev/null || true; done
    if [ -f "$BAK" ]; then
        cp "$BAK" "$NGX" || true
        nginx -t >/dev/null 2>&1 && nginx -s reload || true
    fi
    systemctl stop "$FAILSAFE_UNIT.timer" "$FAILSAFE_UNIT.service" >/dev/null 2>&1 || true
    log "RESTORED (acl + routes v4/v6 + nginx); failsafe cancelled"
}
trap restore EXIT

# Clear any orphaned failsafe from a previous run BEFORE arming ours.
systemctl stop "$FAILSAFE_UNIT.timer" "$FAILSAFE_UNIT.service" >/dev/null 2>&1 || true
systemd-run --on-active=$((CUT_SECONDS + 300))s --unit="$FAILSAFE_UNIT" /bin/bash -c \
    "$RCLI ACL SETUSER default allchannels; \
     for ip in $PEER_IPS; do ip route del blackhole \$ip 2>/dev/null || true; done; \
     for ip in ${PEER_IP6S:-}; do ip -6 route del blackhole \$ip 2>/dev/null || true; done; \
     [ -f $BAK ] && cp $BAK $NGX && nginx -s reload" || true

# --- wait for the trigger head -------------------------------------------
H=""
for _ in $(seq 1 600); do
    H=$(curl -s --max-time 3 "http://127.0.0.1:$RPC_PORT/rpc/head" | python3 -c "import sys,json;print(json.load(sys.stdin)['height'])" 2>/dev/null || true)
    if [ -n "$H" ] && [ $((H % NVALS)) -eq "$SLOT" ]; then break; fi
    sleep 2
done
if [ -z "$H" ]; then log "TRIGGER TIMEOUT — aborting"; exit 1; fi
log "TRIGGER head=$H (H%$NVALS=$((H % NVALS))); this node owns r1 of $((H + 1)) when SLOT=0"

# --- layer 3: nginx — /rpc/gossip/ proxied, rest of /rpc/ -> 444 ----------
cp "$NGX" "$BAK"
if ! python3 - "$NGX" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
old = """    location /rpc/ {
        proxy_pass http://blockchain_rpc/rpc/;"""
new = """    location /rpc/gossip/ {
        proxy_pass http://blockchain_rpc/rpc/gossip/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /rpc/ {
        return 444;"""
assert old in s, "rpc location block not found in nginx config — aborting"
open(p, "w").write(s.replace(old, new, 1))
PY
then
    log "NGINX patch FAILED — aborting cut"
    cp "$BAK" "$NGX"
    exit 1
fi
if ! nginx -t >/dev/null 2>&1; then
    log "NGINX -t FAILED — aborting cut"
    cp "$BAK" "$NGX"
    exit 1
fi
nginx -s reload

# --- layer 2: redis ACL — blocks.* denied, attest/tx channels open -------
$RCLI ACL SETUSER default resetchannels \
    "&consensus.attest_request.$CHAIN" "&consensus.attest_response.$CHAIN" \
    "&transactions" "&transactions.$CHAIN" >/dev/null

# --- layer 1: routes + established-conn sweep -----------------------------
for ip in $PEER_IPS; do
    ip route add blackhole "$ip" 2>/dev/null || true
    ss -K dst "$ip" >/dev/null 2>&1 || true   # kill pre-established conns now
done
for ip in ${PEER_IP6S:-}; do ip -6 route add blackhole "$ip" 2>/dev/null || true; done

log "CUT STARTED for ${CUT_SECONDS}s (v4:$(echo $PEER_IPS | wc -w) blackholed, v6:$(echo ${PEER_IP6S:-none} | wc -w), blocks.* denied, /rpc pulls 444)"

# --- mid-cut snapshot: prove the cut is still in place --------------------
sleep 15
{
    for ip in $PEER_IPS; do ip route get "$ip" 2>&1 | head -1; done
    ss -tn state established | awk 'NR>1 {print $4, $5}' | sort | uniq -c | sort -rn | head -15
    curl -s -o /dev/null -w "self /rpc/head: %{http_code}" --max-time 3 "http://127.0.0.1:$RPC_PORT/rpc/head" || true
} | sed "s/^/SNAPSHOT /" | while read -r line; do log "$line"; done

sleep $((CUT_SECONDS - 15))
log "CUT ENDING"
restore
trap - EXIT
log "DONE — watch journals for 'deferring reorg' then 'peer branch wins ... length'"
