#!/usr/bin/env bash
set -euo pipefail

CHAIN_ID="${CHAIN_ID:-ait-mainnet}"
SERVICE_NAME="${SERVICE_NAME:-aitbc-blockchain-node.service}"
LEADER="${LEADER:-aitbc1}"
NODES_RAW="${NODES:-localhost aitbc1 gitea-runner}"
UTILITY="${UTILITY:-/opt/aitbc/scripts/utils/chain_regen_node.py}"
PYTHON_BIN="${PYTHON_BIN:-/opt/aitbc/venv/bin/python}"
TIMESTAMP="${TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
STARTUP_WAIT_SECONDS="${STARTUP_WAIT_SECONDS:-8}"
FOLLOWER_START_WAIT_SECONDS="${FOLLOWER_START_WAIT_SECONDS:-8}"
VERIFY_RETRIES="${VERIFY_RETRIES:-6}"
VERIFY_RETRY_SECONDS="${VERIFY_RETRY_SECONDS:-10}"

usage() {
  cat <<USAGE
Usage: $0 <preflight|backup|set-roles|stop|reset|start|verify|rollout|clear-roles>

Environment:
  CHAIN_ID=$CHAIN_ID
  SERVICE_NAME=$SERVICE_NAME
  LEADER=$LEADER
  NODES="$NODES_RAW"
  TIMESTAMP=$TIMESTAMP
USAGE
}

node_cmd() {
  local node="$1"
  shift
  if [[ "$node" == "localhost" || "$node" == "local" || "$node" == "$(hostname)" ]]; then
    "$@"
  else
    ssh "$node" "$*"
  fi
}

run_node_utility() {
  local node="$1"
  shift
  node_cmd "$node" "$PYTHON_BIN" "$UTILITY" --chain-id "$CHAIN_ID" --service-name "$SERVICE_NAME" "$@"
}

for_each_node() {
  local action="$1"
  shift
  local node
  for node in $NODES_RAW; do
    echo "===== $node :: $action ====="
    "$@" "$node"
  done
}

preflight_node() {
  run_node_utility "$1" preflight
}

backup_node() {
  run_node_utility "$1" backup --timestamp "$TIMESTAMP"
}

set_role_node() {
  local node="$1"
  if [[ "$node" == "$LEADER" ]]; then
    run_node_utility "$node" set-role leader
  else
    run_node_utility "$node" set-role follower
  fi
}

clear_role_node() {
  run_node_utility "$1" set-role clear
}

stop_node() {
  node_cmd "$1" systemctl stop "$SERVICE_NAME"
}

reset_node() {
  run_node_utility "$1" reset --yes
}

start_leader() {
  echo "===== $LEADER :: start leader ====="
  node_cmd "$LEADER" systemctl start "$SERVICE_NAME"
  sleep "$STARTUP_WAIT_SECONDS"
}

start_followers() {
  local node
  for node in $NODES_RAW; do
    if [[ "$node" == "$LEADER" ]]; then
      continue
    fi
    echo "===== $node :: start follower ====="
    node_cmd "$node" systemctl start "$SERVICE_NAME"
  done
  sleep "$FOLLOWER_START_WAIT_SECONDS"
}

verify_node() {
  run_node_utility "$1" verify --require-nonzero-root
}

verify_node_with_retry() {
  local node="$1"
  local attempt
  for attempt in $(seq 1 "$VERIFY_RETRIES"); do
    if run_node_utility "$node" verify --require-nonzero-root; then
      return 0
    fi
    if [[ "$attempt" == "$VERIFY_RETRIES" ]]; then
      return 1
    fi
    echo "verify failed for $node, retrying in ${VERIFY_RETRY_SECONDS}s (${attempt}/${VERIFY_RETRIES})" >&2
    sleep "$VERIFY_RETRY_SECONDS"
  done
}

case "${1:-}" in
  preflight)
    for_each_node preflight preflight_node
    ;;
  backup)
    for_each_node backup backup_node
    ;;
  set-roles)
    for_each_node set-roles set_role_node
    ;;
  clear-roles)
    for_each_node clear-roles clear_role_node
    ;;
  stop)
    for_each_node stop stop_node
    ;;
  reset)
    for_each_node reset reset_node
    ;;
  start)
    start_leader
    start_followers
    ;;
  verify)
    for_each_node verify verify_node
    ;;
  rollout)
    for_each_node preflight preflight_node
    for_each_node set-roles set_role_node
    for_each_node backup backup_node
    for_each_node stop stop_node
    for_each_node reset reset_node
    start_leader
    start_followers
    for_each_node verify verify_node_with_retry
    ;;
  *)
    usage
    exit 64
    ;;
esac
