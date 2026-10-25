#!/bin/sh
# failover-preflight.sh — read-only go/no-go check for the #392 hub1
# failover drill. Prints PASS/FAIL per row; exits 1 on any FAIL.
# NEVER runs a mutating command: no systemctl start|stop|restart|enable|
# disable, no writes, no deletes. stdout only.
#
# Usage: failover-preflight.sh [--expected-sha256 <live-site-sha>]
# Env: HOSTS="hub hub1 node0 node1 node2"  NGINX_SITE=/etc/nginx/sites-enabled/aitbc
set -euo pipefail

HOSTS="${HOSTS:-hub hub1 node0 node1 node2}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/aitbc}"
EXPECTED_SHA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --expected-sha256) EXPECTED_SHA="${2:-}"; shift 2 ;;
    --expected-sha256=*) EXPECTED_SHA="${1#*=}"; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

fails=0
row() { # row <name> <PASS|FAIL> <detail>
  printf "%-28s %s %s\n" "$1" "$2" "$3"
  [ "$2" = FAIL ] && fails=$((fails + 1))
  return 0
}

sshro() { ssh -o BatchMode=yes -o ConnectTimeout=8 "$1" "$2" 2>/dev/null || true; }

# 1. chain heads equal on all hosts (sqlite mode=ro; never `aitbc blockchain height`)
prev=""
allok=1
for h in $HOSTS; do
  out=$(sshro "$h" "sqlite3 'file:/var/lib/aitbc/data/bc-2/chain.db?mode=ro' 'select max(height),substr(hash,1,14) from block order by height desc limit 1'")
  if [ -z "$out" ]; then row "head:$h" FAIL "ssh/sqlite failed"; allok=0; continue; fi
  [ -z "$prev" ] || [ "$prev" = "$out" ] || allok=0
  prev="$out"
  row "head:$h" PASS "$out"
done
if [ "$allok" = 1 ] && [ -n "$prev" ]; then
  row "heads-equal" PASS "$prev"
else
  row "heads-equal" FAIL "divergent-or-missing"
fi

# 2. hub1 node/rpc start times (soak-clock judgement belongs to the sheet)
ts=$(sshro hub1 "systemctl show aitbc-blockchain-node -p ActiveEnterTimestamp --value")
row "hub1-node-start" PASS "${ts:-unread}"

# 3. hub1 failed aitbc units = 0
n=$(sshro hub1 "systemctl list-units --failed --no-legend 'aitbc-*' | wc -l")
if [ "$n" = "0" ]; then row "hub1-failed-units" PASS "0"; else row "hub1-failed-units" FAIL "$n failed"; fi

# 4. hub1 memory: oom_kill=0 and current under cap
ev=$(sshro hub1 "cat /sys/fs/cgroup/memory.events | tr ' ' '\n' | grep '^oom_kill=' | cut -d= -f2")
cur=$(sshro hub1 "cat /sys/fs/cgroup/memory.current")
max=$(sshro hub1 "cat /sys/fs/cgroup/memory.max")
if [ "$ev" = "0" ] && [ "${cur:-0}" -lt "${max:-0}" ] 2>/dev/null && [ -n "$max" ]; then
  row "hub1-memory" PASS "oom_kill=0 cur=$cur max=$max"
else
  row "hub1-memory" FAIL "oom_kill=${ev:-?} cur=${cur:-?} max=${max:-?}"
fi

# 5. ns3 swap USED below the 300M flag value
used=$(sshro ns3-root "sudo -n swapon --show=USED --bytes --noheadings" | awk '{s+=$1} END{print s+0}')
if [ "${used:-999999999}" -lt 300000000 ] 2>/dev/null; then
  row "ns3-swap" PASS "${used}B"
else
  row "ns3-swap" FAIL "${used:-?}B (>=300M flag)"
fi

# 6. hub nginx site sha256 (Round-6 variant validity)
sha=$(sshro hub "sha256sum $NGINX_SITE | cut -d' ' -f1")
if [ -n "$EXPECTED_SHA" ]; then
  if [ "$sha" = "$EXPECTED_SHA" ]; then
    row "hub-nginx-sha" PASS "$sha"
  else
    row "hub-nginx-sha" FAIL "${sha:-?} != $EXPECTED_SHA"
  fi
else
  row "hub-nginx-sha" PASS "${sha:-unread} (no expected value supplied — eyeball vs ledger)"
fi

# 7. hub1 standby services: 8 LINE-4 units active, keep-offs inactive
act=$(sshro hub1 "systemctl is-active aitbc-coordinator-api aitbc-market aitbc-agent-coordinator aitbc-pool-hub aitbc-api-gateway aitbc-blockchain-event-bridge aitbc-blockchain-p2p aitbc-ops-signer | grep -c '^active'")
kee=$(sshro hub1 "systemctl is-active aitbc-exchange aitbc-bridge-monitor | grep -c '^inactive'")
if [ "$act" = "8" ] && [ "$kee" = "2" ]; then
  row "hub1-services" PASS "8 active, 2 keep-off"
else
  row "hub1-services" FAIL "active=${act:-?}/8 keep-off=${kee:-?}/2"
fi

# 8. bridge_deposits.db sizes both sides (drift report; informational)
bd=$(sshro hub "stat -c %s /var/lib/aitbc/data/bridge_deposits.db")
bd1=$(sshro hub1 "stat -c %s /var/lib/aitbc/data/bridge_deposits.db")
row "bridge-deposits-size" PASS "hub=${bd:-?} hub1=${bd1:-?} (re-snapshot at real cut)"

# 9. hub1 public vhost canary (3 read-only paths through the public name)
p=0
for path in /rpc/head /explorer-api/api/chain/head /explorer-api/health; do
  code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "https://hub1.aitbc.bubuit.net$path" || true)
  [ "$code" = "200" ] && p=$((p + 1))
done
if [ "$p" = "3" ]; then row "hub1-canary" PASS "3/3 200"; else row "hub1-canary" FAIL "$p/3 200"; fi

echo "---"
if [ "$fails" -eq 0 ]; then
  echo "PREFLIGHT PASS"
else
  echo "PREFLIGHT FAIL ($fails rows)"
  exit 1
fi
