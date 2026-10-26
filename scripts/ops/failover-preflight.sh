#!/bin/sh
# failover-preflight.sh — read-only go/no-go check for the #392 hub1
# failover drill. Prints PASS/FAIL per row; exits 1 on any FAIL.
# NEVER runs a mutating command: no systemctl start|stop|restart|enable|
# disable, no writes, no deletes. stdout only.
#
# Usage: failover-preflight.sh [--expected-sha256 <live-site-sha>]
#        [--soak-node-start "<ActiveEnterTimestamp to require>"]
# Env: HOSTS="hub hub1 node0 node1 node2"  CHAIN_ID=bc-2
#      NGINX_SITE=/etc/nginx/sites-enabled/aitbc
set -euo pipefail

HOSTS="${HOSTS:-hub hub1 node0 node1 node2}"
CHAIN_ID="${CHAIN_ID:-bc-2}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/aitbc}"
EXPECTED_SHA=""
SOAK_NODE_START="${SOAK_NODE_START:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --expected-sha256) EXPECTED_SHA="${2:-}"; shift 2 ;;
    --expected-sha256=*) EXPECTED_SHA="${1#*=}"; shift ;;
    --soak-node-start) SOAK_NODE_START="${2:-}"; shift 2 ;;
    --soak-node-start=*) SOAK_NODE_START="${1#*=}"; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

fails=0
row() { # row <name> <PASS|FAIL|INFO> <detail>
  printf "%-28s %s %s\n" "$1" "$2" "$3"
  [ "$2" = FAIL ] && fails=$((fails + 1))
  return 0
}

# ssh read that FAILS LOUDLY: prints the output, or nothing on failure —
# callers must treat empty as a failed read, never as a passing zero.
sshro() { ssh -o BatchMode=yes -o ConnectTimeout=8 "$1" "$2" 2>/dev/null || true; }

# --- head reads, one ssh per host but with a re-check pass when the first
# sweep disagrees (a block landing mid-run must not read as a fork).
heads_scan() {
  for h in $HOSTS; do
    out=$(sshro "$h" "sqlite3 'file:/var/lib/aitbc/data/$CHAIN_ID/chain.db?mode=ro' 'select max(height),substr(hash,1,14) from block order by height desc limit 1'")
    printf '%s|%s\n' "$h" "$out"
  done
}

sweep=$(heads_scan)
ok_all=1; firstv=""; hprev=""
for pair in $(printf '%s\n' "$sweep" | tr ' ' '_'); do
  h=${pair%%|*}; v=${pair#*|}; h=${h%|}
  if [ -z "$v" ]; then row "head:$h" FAIL "read failed"; ok_all=0; continue; fi
  if [ -z "$firstv" ]; then firstv="$v"; hprev="$h"; else
    if [ "$v" != "$firstv" ]; then
      # re-read both once: a new block mid-sweep is not divergence
      a=$(sshro "$hprev" "sqlite3 'file:/var/lib/aitbc/data/$CHAIN_ID/chain.db?mode=ro' 'select max(height),substr(hash,1,14) from block order by height desc limit 1'")
      b=$(sshro "$h" "sqlite3 'file:/var/lib/aitbc/data/$CHAIN_ID/chain.db?mode=ro' 'select max(height),substr(hash,1,14) from block order by height desc limit 1'")
      if [ -z "$a" ] || [ -z "$b" ] || [ "$a" != "$b" ]; then ok_all=0; fi
      v="$b"
    fi
  fi
  row "head:$h" PASS "$v"
done
if [ "$ok_all" = 1 ] && [ -n "$firstv" ]; then row "heads-equal" PASS "$firstv"; else row "heads-equal" FAIL "divergent-or-missing"; fi

# --- one ssh for all hub1 unit/cgroup reads (fewer calls, one failure point)
hub1blob=$(sshro hub1 'echo "NODE_TS=$(systemctl show aitbc-blockchain-node -p ActiveEnterTimestamp --value)"; echo "FAILED=$(systemctl list-units --failed --no-legend aitbc-* | wc -l)"; echo "--EVENTS--"; cat /sys/fs/cgroup/memory.events; echo "--MEM--"; cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max; echo "--ACT--"; systemctl is-active aitbc-coordinator-api aitbc-market aitbc-agent-coordinator aitbc-pool-hub aitbc-api-gateway aitbc-blockchain-event-bridge aitbc-blockchain-p2p aitbc-ops-signer | grep -c "^active"; systemctl is-active aitbc-exchange aitbc-bridge-monitor | grep -c "^inactive"')

if [ -z "$hub1blob" ]; then
  row "hub1-reads" FAIL "single ssh read failed — cannot verify node-start, failed units, memory, services"
else
  ts=$(printf '%s\n' "$hub1blob" | sed -n 's/^NODE_TS=//p')
  if [ -n "$SOAK_NODE_START" ]; then
    [ "$ts" = "$SOAK_NODE_START" ] && row "hub1-node-start" PASS "$ts" \
      || row "hub1-node-start" FAIL "$ts (expected $SOAK_NODE_START — clock reset?)"
  else
    [ -n "$ts" ] && row "hub1-node-start" PASS "$ts (no expected value — eyeball vs ledger)" \
      || row "hub1-node-start" FAIL "unread"
  fi

  n=$(printf '%s\n' "$hub1blob" | sed -n 's/^FAILED=//p')
  [ "$n" = "0" ] && row "hub1-failed-units" PASS "0" || row "hub1-failed-units" FAIL "${n:-unread} failed"

  # memory.events parsed LOCALLY so the stub/test exercises the real format
  ev=$(printf '%s\n' "$hub1blob" | sed -n '/--EVENTS--/,/--MEM--/p' | awk '/^oom_kill/{print $2}')
  cur=$(printf '%s\n' "$hub1blob" | sed -n '/--MEM--/,/--ACT--/p' | sed -n '2p')
  max=$(printf '%s\n' "$hub1blob" | sed -n '/--MEM--/,/--ACT--/p' | sed -n '3p')
  if [ "$ev" = "0" ] && [ -n "$cur" ] && [ -n "$max" ] && [ "$cur" -lt "$max" ] 2>/dev/null; then
    row "hub1-memory" PASS "oom_kill=0 cur=$cur max=$max"
  else
    row "hub1-memory" FAIL "oom_kill=${ev:-unread} cur=${cur:-?} max=${max:-?}"
  fi

  act=$(printf '%s\n' "$hub1blob" | sed -n '/--ACT--/,$p' | sed -n '2p')
  kee=$(printf '%s\n' "$hub1blob" | sed -n '/--ACT--/,$p' | sed -n '3p')
  if [ "$act" = "8" ] && [ "$kee" = "2" ]; then
    row "hub1-services" PASS "8 active, 2 keep-off"
  else
    row "hub1-services" FAIL "active=${act:-?}/8 keep-off=${kee:-?}/2"
  fi
fi

# --- ns3 swap: a failed read FAILS (empty is not zero)
swap_raw=$(sshro ns3-root "sudo -n swapon --show=USED --bytes --noheadings")
if [ -z "$swap_raw" ]; then
  row "ns3-swap" FAIL "read failed — swap not verified"
else
  used=$(printf '%s\n' "$swap_raw" | awk '{s+=$1} END{print s+0}')
  if [ "$used" -lt 300000000 ]; then row "ns3-swap" PASS "${used}B"; else row "ns3-swap" FAIL "${used}B (>=300M flag)"; fi
fi

# --- hub nginx sha: an unread file FAILS, not a silent pass
sha=$(sshro hub "sha256sum $NGINX_SITE | cut -d' ' -f1")
if [ -z "$sha" ]; then
  row "hub-nginx-sha" FAIL "read failed — variant validity unknown"
elif [ -n "$EXPECTED_SHA" ] && [ "$sha" != "$EXPECTED_SHA" ]; then
  row "hub-nginx-sha" FAIL "$sha != $EXPECTED_SHA"
elif [ -n "$EXPECTED_SHA" ]; then
  row "hub-nginx-sha" PASS "$sha"
else
  row "hub-nginx-sha" PASS "$sha (no expected value — eyeball vs ledger)"
fi

# --- bridge_deposits drift: informational
bd=$(sshro hub "stat -c %s /var/lib/aitbc/data/bridge_deposits.db")
bd1=$(sshro hub1 "stat -c %s /var/lib/aitbc/data/bridge_deposits.db")
row "bridge-deposits-size" INFO "hub=${bd:-?} hub1=${bd1:-?} (re-snapshot at real cut)"

# --- hub1 public vhost canary
p=0
for path in /rpc/head /explorer-api/api/chain/head /explorer-api/health; do
  code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "https://hub1.aitbc.bubuit.net$path" || true)
  [ "$code" = "200" ] && p=$((p + 1))
done
[ "$p" = "3" ] && row "hub1-canary" PASS "3/3 200" || row "hub1-canary" FAIL "$p/3 200"

echo "---"
if [ "$fails" -eq 0 ]; then
  echo "PREFLIGHT PASS"
else
  echo "PREFLIGHT FAIL ($fails rows)"
  exit 1
fi
