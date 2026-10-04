#!/bin/bash
# Dry-run proof for the DISABLED_SERVICES guard (link-systemd.sh +
# update.sh step 4). Runs the real, unmodified scripts against a sandboxed
# systemd dir with a stubbed systemctl — nothing outside the temp dir is
# touched. Exits non-zero on any failed assertion.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SBX="$(mktemp -d /tmp/t104-guard.XXXXXX)"
trap 'rm -rf "$SBX"' EXIT

FAILS=0
check() { # description command...
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $desc"
    else
        echo "  FAIL: $desc"
        FAILS=$((FAILS + 1))
    fi
}
log_has()    { grep -qF "$1" "$STUB_LOG"; }
log_hasnt()  { ! grep -qF "$1" "$STUB_LOG"; }
file_there() { [ -e "$1" ]; }
file_gone()  { [ ! -e "$1" ]; }

# --- sandbox -------------------------------------------------------------
STUB_BIN="$SBX/bin"
STUB_STATE="$SBX/state"
STUB_LOG="$STUB_STATE/systemctl.log"
SYSTEMD_DIR="$SBX/systemd"
ETC_DIR="$SBX/etc"
FAKE_REPO="$SBX/repo"
mkdir -p "$STUB_BIN" "$STUB_STATE" "$SYSTEMD_DIR" "$ETC_DIR" \
         "$FAKE_REPO/scripts/utils" "$FAKE_REPO/apps/market" \
         "$FAKE_REPO/apps/node" "$FAKE_REPO/apps/exchange"

cat > "$STUB_BIN/systemctl" <<'EOF'
#!/bin/bash
echo "systemctl $*" >> "$STUB_LOG"
cmd="${1:-}"; shift || true
case "$cmd" in
    cat)           exit 1 ;;
    daemon-reload) exit 0 ;;
    --version)     echo "systemd 252"; exit 0 ;;
    show)
        prop=""; unit=""
        while [ $# -gt 0 ]; do
            case "$1" in
                -p)      prop="$2"; shift 2 ;;
                --value) shift ;;
                *)       unit="$1"; shift ;;
            esac
        done
        case "$prop" in
            LoadState) echo "not-found" ;;
            *)         echo "" ;;
        esac
        exit 0 ;;
    is-enabled)
        grep -qxF "$1" "$STUB_STATE/enabled" 2>/dev/null ;;
    enable)
        echo "$1" >> "$STUB_STATE/enabled"
        echo "Created symlink /etc/systemd/system/multi-user.target.wants/$1 -> /etc/systemd/system/$1." ;;
    disable)
        if [ -f "$STUB_STATE/enabled" ]; then
            grep -vxF "$1" "$STUB_STATE/enabled" > "$STUB_STATE/enabled.new" || true
            mv -f "$STUB_STATE/enabled.new" "$STUB_STATE/enabled"
        fi
        exit 0 ;;
    is-active) exit 1 ;;
    *)         exit 0 ;;
esac
EOF
chmod +x "$STUB_BIN/systemctl"
export STUB_LOG STUB_STATE
: > "$STUB_LOG"; : > "$STUB_STATE/enabled"

mkunit() { # repo-subdir unit-file  — minimal unit with [Install]
    cat > "$FAKE_REPO/apps/$1/$2" <<EOF
[Unit]
Description=fake $2
[Service]
ExecStart=/bin/true
[Install]
WantedBy=multi-user.target
EOF
}
mkunit market   aitbc-market.service
mkunit node     aitbc-blockchain-node.service
mkunit exchange aitbc-exchange.service

# hub1-shaped node.env: follower role, EXTRA_SERVICES still naming demoted
# units, and the new DISABLED_SERVICES list that must override it.
cat > "$ETC_DIR/node.env" <<'EOF'
BLOCKCHAIN_MODE=follower
MARKET_ROLE=customer
HARDWARE_PROFILE=nogpu
EXTRA_SERVICES="aitbc-market"
DISABLED_SERVICES="aitbc-market aitbc-exchange"
EOF
touch "$ETC_DIR/blockchain.env"

echo "== link-systemd.sh (sandboxed, real script) =="
cp "$REPO_ROOT/scripts/utils/link-systemd.sh" "$FAKE_REPO/scripts/utils/"
PATH="$STUB_BIN:$PATH" \
AITBC_SYSTEMD_DIR="$SYSTEMD_DIR" \
AITBC_TMPFILES_DIR="$SBX/tmpfiles" \
AITBC_NODE_ENV_FILE="$ETC_DIR/node.env" \
    bash "$FAKE_REPO/scripts/utils/link-systemd.sh" > "$SBX/link.out" 2>&1 \
    || { echo "  FAIL: link-systemd.sh exited $?"; FAILS=$((FAILS+1)); }

check "allowed unit linked"              file_there "$SYSTEMD_DIR/aitbc-blockchain-node.service"
check "excluded unit not linked"         file_gone  "$SYSTEMD_DIR/aitbc-market.service"
check "excluded unit not linked (2)"     file_gone  "$SYSTEMD_DIR/aitbc-exchange.service"
check "allowed unit enabled"             log_has    "enable aitbc-blockchain-node.service"
check "excluded unit never enabled"      log_hasnt  "enable aitbc-market.service"
check "exclusion beat EXTRA_SERVICES"    file_gone  "$SYSTEMD_DIR/aitbc-market.service"

echo "== update.sh enable_services (sourced, real code) =="
SYSTEMD2="$SBX/systemd2"; mkdir -p "$SYSTEMD2"
cp "$FAKE_REPO/apps/market/aitbc-market.service" "$SYSTEMD2/"
cp "$FAKE_REPO/apps/node/aitbc-blockchain-node.service" "$SYSTEMD2/"
echo "aitbc-market.service" >> "$STUB_STATE/enabled"   # pre-enabled → must be disabled
: > "$STUB_LOG"

(
    set +e   # update.sh itself does not use -e; source and call without it
    export AITBC_ROOT="$FAKE_REPO"   # no agent_followup.sh here → hook skipped
    export AITBC_SYSTEMD_DIR="$SYSTEMD2"
    export AITBC_NODE_ENV_FILE="$ETC_DIR/node.env"
    export AITBC_BLOCKCHAIN_ENV_FILE="$ETC_DIR/blockchain.env"
    export PATH="$STUB_BIN:$PATH"
    source "$REPO_ROOT/scripts/deployment/update.sh"
    enable_services
) > "$SBX/enable.out" 2>&1 || { echo "  FAIL: enable_services exited $?"; FAILS=$((FAILS+1)); }

check "excluded unit was disabled"       log_has    "disable aitbc-market.service"
check "excluded unit never enabled"      log_hasnt  "enable aitbc-market.service"
check "allowed unit enabled"             log_has    "enable aitbc-blockchain-node.service"
grep -q "DISABLED_SERVICES" "$SBX/enable.out" \
    && echo "  PASS: exclusion logged" || { echo "  FAIL: exclusion not logged"; FAILS=$((FAILS+1)); }

echo "== env-var DISABLED_SERVICES beats the file =="
: > "$STUB_LOG"
(
    set +e
    export AITBC_ROOT="$FAKE_REPO"
    export AITBC_SYSTEMD_DIR="$SYSTEMD2"
    export AITBC_NODE_ENV_FILE="$ETC_DIR/node.env"
    export AITBC_BLOCKCHAIN_ENV_FILE="$ETC_DIR/blockchain.env"
    export DISABLED_SERVICES="aitbc-blockchain-node"
    export PATH="$STUB_BIN:$PATH"
    source "$REPO_ROOT/scripts/deployment/update.sh"
    enable_services
) >> "$SBX/enable.out" 2>&1 || { echo "  FAIL: second enable_services exited $?"; FAILS=$((FAILS+1)); }

check "env list honoured"                log_hasnt  "enable aitbc-blockchain-node.service"
check "env list overrides file"          log_has    "enable aitbc-market.service"

echo
if [ "$FAILS" -eq 0 ]; then
    echo "ALL CHECKS PASSED"
else
    echo "$FAILS CHECK(S) FAILED"
    echo "--- link-systemd output ---"; tail -20 "$SBX/link.out" 2>/dev/null
    echo "--- enable_services output ---"; cat "$SBX/enable.out" 2>/dev/null
    exit 1
fi
