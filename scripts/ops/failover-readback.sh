#!/bin/bash
# Hub→hub1 failover public read-back, READ-ONLY (see docs/ops/failover-runbook.md). usage: failover-readback.sh <forward|reverse|pre>
# Each GET goes through hub's public front with a unique User-Agent; hub1's
# access log (format aitbc_scrub logs $http_user_agent) then proves which
# host served it. forward: every FLIP path must appear on hub1, no STAY path.
# reverse/pre: nothing may appear on hub1.
set -euo pipefail
PH=${1:?phase}; N="aitbc-fo-$PH-$(date +%s)"; F="${FAILOVER_FRONT:-https://hub.aitbc.bubuit.net}"
FLIP="/rpc/head /rpc/blocks/1 /rpc/mempool /explorer-api/health /explorer-api/api/chain/head /explorer-api/api/blocks/1 /explorer-api/api/messages /explorer-api/api/messages/topics /explorer-api/api/messages/state"
STAY="/rpc/join /rpc/subscribers /rpc/market/listings /rpc/islands /rpc/chains /rpc/network-info /rpc/messaging/ /rpc/contracts/messaging/ /explorer-api/api/journal/counts /explorer-api/api/alerts /v1/payments /v1/jobs /v1/market/plugins /api/health /api/v1/agent/ /api/v1/agent/messages/ /pool-hub/health /exchange-api/orderbook /v1/exchange/history /v1/bridge/deposits /v1/metrics /dashboard/ /"
echo "== readback $PH $(date '+%F %T %Z') / $(date -u '+%T UTC') ua=$N"
for c in FLIP STAY; do for p in ${!c}; do
  printf '%s %-38s ' $c $p; curl -s -m 15 -o /dev/null -A "$N-$c" -w '%{http_code} %{time_total}s\n' "$F$p"; done; done
sleep 2
f=$(ssh -o BatchMode=yes hub1 "sudo -n grep -c -- '$N-FLIP' /var/log/nginx/access.log"); s=$(ssh -o BatchMode=yes hub1 "sudo -n grep -c -- '$N-STAY' /var/log/nginx/access.log")
nf=$(echo $FLIP | wc -w)
echo "hub1 served FLIP=$f/$nf STAY=$s"
case $PH in forward) [ "$f" = "$nf" ] && [ "$s" = 0 ] && echo PASS || echo FAIL;; *) [ "$f" = 0 ] && [ "$s" = 0 ] && echo PASS || echo FAIL;; esac
