#!/bin/bash
# Dry-run proof for the selective reconcile sweep in link-systemd.sh
# (Task 108). The 2026-10-04 deploy showed the old blanket
# `find ... -name 'aitbc-*' -delete` unlinked every operator-linked repo
# unit the role model did not list — escrow-settlements, journal-errors,
# prometheus-watch, authority-balances went dark fleet-wide.
#
# Runs the real, unmodified script against a sandboxed systemd dir with a
# stubbed systemctl — nothing outside the temp dir is touched. Exits
# non-zero on any failed assertion.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SBX="$(mktemp -d /tmp/t108-preserve.XXXXXX)"
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
file_there() { [ -e "$1" ] || [ -L "$1" ]; }
file_gone()  { [ ! -e "$1" ] && [ ! -L "$1" ]; }
log_has()    { grep -qF "$1" "$STUB_LOG"; }
log_hasnt()  { ! grep -qF "$1" "$STUB_LOG"; }

# --- sandbox -------------------------------------------------------------
STUB_BIN="$SBX/bin"
STUB_STATE="$SBX/state"
STUB_LOG="$STUB_STATE/systemctl.log"
SYSTEMD_DIR="$SBX/systemd"
ETC_DIR="$SBX/etc"
FAKE_REPO="$SBX/repo"
mkdir -p "$STUB_BIN" "$STUB_STATE" "$SYSTEMD_DIR" "$ETC_DIR" \
         "$FAKE_REPO/scripts/utils" "$FAKE_REPO/scripts/monitoring" \
         "$FAKE_REPO/scripts/config" "$FAKE_REPO/apps/market" \
         "$FAKE_REPO/apps/node" "$FAKE_REPO/apps/explorer" \
         "$FAKE_REPO/apps/coordinator-api"

# systemctl stub: LoadState mirrors the *sandbox* systemd dir, so the stale
# .wants/ sweep behaves the same way it would against real systemd.
cat > "$STUB_BIN/systemctl" <<'EOF'
#!/bin/bash
echo "systemctl $*" >> "$STUB_LOG"
cmd="${1:-}"; shift || true
case "$cmd" in
    cat)           exit 1 ;;            # no redis-server in the sandbox
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
            LoadState)
                if [ -e "$STUB_SYSTEMD_DIR/$unit" ] || [ -L "$STUB_SYSTEMD_DIR/$unit" ]; then
                    echo "linked"
                else
                    echo "not-found"
                fi ;;
            *) echo "" ;;
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
    *)         exit 0 ;;
esac
EOF
chmod +x "$STUB_BIN/systemctl"
export STUB_LOG STUB_STATE STUB_SYSTEMD_DIR="$SYSTEMD_DIR"
: > "$STUB_LOG"; : > "$STUB_STATE/enabled"

# --- fake repo units -----------------------------------------------------
mkunit() { # repo-subdir unit-file
    cat > "$FAKE_REPO/$1/$2" <<EOF
[Unit]
Description=fake $2
[Service]
ExecStart=/bin/true
[Install]
WantedBy=multi-user.target
EOF
}
mktimer() { # repo-subdir base-name — timer + service pair
    cat > "$FAKE_REPO/$1/$2.timer" <<EOF
[Unit]
Description=fake $2 timer
[Timer]
OnBootSec=1min
[Install]
WantedBy=timers.target
EOF
    cat > "$FAKE_REPO/$1/$2.service" <<EOF
[Unit]
Description=fake $2
[Service]
ExecStart=/bin/true
EOF
}
# Modeled services
mkunit  apps/node             aitbc-blockchain-node.service
mkunit  apps/market           aitbc-market.service
mkunit  apps/explorer         aitbc-blockchain-explorer.service
mkunit  apps/coordinator-api  aitbc-coordinator-api.service
# Monitoring units as they exist in the real scripts/monitoring/
mktimer scripts/monitoring    aitbc-escrow-settlements
mktimer scripts/monitoring    aitbc-journal-errors
mktimer scripts/monitoring    aitbc-authority-balances
mkunit  scripts/monitoring    aitbc-prometheus-watch.service
mktimer scripts/monitoring    aitbc-chain-isolation-monitor
mktimer scripts/monitoring    aitbc-memory-monitor
# Deliberately unmodeled repo unit — the preserve-passthrough case
mktimer scripts/monitoring    aitbc-native-energy-rate-refresh
# Unmodeled repo timer with NO service — exercises the orphan-timer guard
cat > "$FAKE_REPO/scripts/monitoring/aitbc-lonely.timer" <<'EOF'
[Unit]
Description=fake lonely timer
[Timer]
OnBootSec=1min
[Install]
WantedBy=timers.target
EOF

run_link() { # label — runs the real script against the sandbox
    local label="$1"
    : > "$STUB_LOG"
    if ! PATH="$STUB_BIN:$PATH" \
        AITBC_SYSTEMD_DIR="$SYSTEMD_DIR" \
        AITBC_TMPFILES_DIR="$SBX/tmpfiles" \
        AITBC_ETC_DIR="$ETC_DIR" \
        AITBC_NODE_ENV_FILE="$ETC_DIR/node.env" \
        AITBC_BLOCKCHAIN_ENV_FILE="$ETC_DIR/blockchain.env" \
        bash "$FAKE_REPO/scripts/utils/link-systemd.sh" > "$SBX/link-$label.out" 2>&1; then
        echo "  FAIL: link-systemd.sh ($label) exited $?"
        FAILS=$((FAILS+1))
    fi
}

mkrole() { # blockchain_mode market_role hardware [extra lines]
    cat > "$ETC_DIR/node.env" <<EOF
BLOCKCHAIN_MODE=$1
MARKET_ROLE=$2
HARDWARE_PROFILE=$3
${4:-}
EOF
    : > "$ETC_DIR/blockchain.env"
}

cp "$REPO_ROOT/scripts/utils/link-systemd.sh" "$FAKE_REPO/scripts/utils/"

# =========================================================================
echo "== role: follower:customer:nogpu — monitoring units linked, preserve works =="
mkrole follower customer nogpu
# Pre-linked operator units: one unmodeled (must survive), one modeled but
# role-excluded (must be dropped), plus foreign/dangling entries.
ln -sf "$FAKE_REPO/scripts/monitoring/aitbc-native-energy-rate-refresh.timer" "$SYSTEMD_DIR/"
ln -sf "$FAKE_REPO/scripts/monitoring/aitbc-native-energy-rate-refresh.service" "$SYSTEMD_DIR/"
ln -sf "$FAKE_REPO/apps/market/aitbc-market.service" "$SYSTEMD_DIR/aitbc-market.service"
mkdir -p "$SBX/foreign-units"
printf '[Unit]\n[Service]\nExecStart=/bin/true\n' > "$SBX/foreign-units/aitbc-foreign.service"
ln -sf "$SBX/foreign-units/aitbc-foreign.service" "$SYSTEMD_DIR/aitbc-foreign.service"
ln -sf /nonexistent/path/aitbc-stale.service "$SYSTEMD_DIR/aitbc-stale.service"
printf '[Unit]\n[Service]\nExecStart=/bin/true\n' > "$SYSTEMD_DIR/aitbc-manual.service"
mkdir -p "$SYSTEMD_DIR/timers.target.wants"
ln -sf "$FAKE_REPO/scripts/monitoring/aitbc-native-energy-rate-refresh.timer" \
       "$SYSTEMD_DIR/timers.target.wants/aitbc-native-energy-rate-refresh.timer"

run_link follower

check "follower: escrow-settlements timer linked"  file_there "$SYSTEMD_DIR/aitbc-escrow-settlements.timer"
check "follower: escrow-settlements svc linked"    file_there "$SYSTEMD_DIR/aitbc-escrow-settlements.service"
check "follower: journal-errors linked"            file_there "$SYSTEMD_DIR/aitbc-journal-errors.timer"
check "follower: prometheus-watch linked"          file_there "$SYSTEMD_DIR/aitbc-prometheus-watch.service"
check "follower: authority-balances NOT linked"    file_gone  "$SYSTEMD_DIR/aitbc-authority-balances.timer"
check "unmodeled operator unit preserved"          file_there "$SYSTEMD_DIR/aitbc-native-energy-rate-refresh.timer"
check "preserved unit keeps .wants entry"          file_there "$SYSTEMD_DIR/timers.target.wants/aitbc-native-energy-rate-refresh.timer"
check "role-excluded modeled unit removed"         file_gone  "$SYSTEMD_DIR/aitbc-market.service"
check "dangling link removed"                      file_gone  "$SYSTEMD_DIR/aitbc-stale.service"
check "foreign (non-repo) link kept"               file_there "$SYSTEMD_DIR/aitbc-foreign.service"
check "regular operator file kept"                 file_there "$SYSTEMD_DIR/aitbc-manual.service"

# =========================================================================
echo "== role: hub:customer:nogpu — hub set, no follower-only units =="
rm -rf "$SYSTEMD_DIR"; mkdir -p "$SYSTEMD_DIR"
mkrole hub customer nogpu
run_link hub
check "hub: authority-balances linked"             file_there "$SYSTEMD_DIR/aitbc-authority-balances.timer"
check "hub: authority-balances svc linked"         file_there "$SYSTEMD_DIR/aitbc-authority-balances.service"
check "hub: escrow-settlements linked"             file_there "$SYSTEMD_DIR/aitbc-escrow-settlements.timer"
check "hub: journal-errors linked"                 file_there "$SYSTEMD_DIR/aitbc-journal-errors.timer"
check "hub: prometheus-watch NOT linked"           file_gone  "$SYSTEMD_DIR/aitbc-prometheus-watch.service"
check "hub: coordinator-api linked"                file_there "$SYSTEMD_DIR/aitbc-coordinator-api.service"
check "hub: blockchain-explorer linked"            file_there "$SYSTEMD_DIR/aitbc-blockchain-explorer.service"
check "hub: timer enables logged"                  log_has    "enable aitbc-escrow-settlements.timer"

# =========================================================================
echo "== role: follower:shop:gpu — validator/shop shape =="
rm -rf "$SYSTEMD_DIR"; mkdir -p "$SYSTEMD_DIR"
mkrole follower shop gpu
run_link shop
check "shop: prometheus-watch linked"              file_there "$SYSTEMD_DIR/aitbc-prometheus-watch.service"
check "shop: market linked"                        file_there "$SYSTEMD_DIR/aitbc-market.service"
check "shop: coordinator-api linked"               file_there "$SYSTEMD_DIR/aitbc-coordinator-api.service"
check "shop: authority-balances NOT linked"        file_gone  "$SYSTEMD_DIR/aitbc-authority-balances.timer"

# =========================================================================
echo "== orphan timer guard =="
rm -rf "$SYSTEMD_DIR"; mkdir -p "$SYSTEMD_DIR"
mkrole follower customer nogpu
# unmodeled timer pair survives when complete; a timer without its service
# file in the repo is preserved on link but dropped by the pair check.
ln -sf "$FAKE_REPO/scripts/monitoring/aitbc-lonely.timer" "$SYSTEMD_DIR/aitbc-lonely.timer"
ln -sf "$FAKE_REPO/scripts/monitoring/aitbc-native-energy-rate-refresh.timer" "$SYSTEMD_DIR/"
ln -sf "$FAKE_REPO/scripts/monitoring/aitbc-native-energy-rate-refresh.service" "$SYSTEMD_DIR/"
run_link orphan
check "complete preserved pair survives"           file_there "$SYSTEMD_DIR/aitbc-native-energy-rate-refresh.timer"
check "orphan timer removed"                       file_gone  "$SYSTEMD_DIR/aitbc-lonely.timer"

# =========================================================================
echo "== DISABLED_SERVICES wins over preserve =="
rm -rf "$SYSTEMD_DIR"; mkdir -p "$SYSTEMD_DIR"
mkrole follower customer nogpu 'DISABLED_SERVICES="aitbc-native-energy-rate-refresh aitbc-journal-errors"'
ln -sf "$FAKE_REPO/scripts/monitoring/aitbc-native-energy-rate-refresh.timer" "$SYSTEMD_DIR/"
ln -sf "$FAKE_REPO/scripts/monitoring/aitbc-native-energy-rate-refresh.service" "$SYSTEMD_DIR/"
run_link disabled
check "DISABLED unmodeled unit removed"            file_gone  "$SYSTEMD_DIR/aitbc-native-energy-rate-refresh.timer"
check "DISABLED modeled unit not relinked"         file_gone  "$SYSTEMD_DIR/aitbc-journal-errors.timer"
check "DISABLED unit never enabled"                log_hasnt  "enable aitbc-journal-errors.timer"

# =========================================================================
echo "== no role files — follower:customer:nogpu defaults =="
# get_node_role() always resolves a spec: with no env files at all the
# defaults are follower:customer:nogpu — the "all" branch is only reachable
# by calling get_allowed_services "all" directly.
rm -rf "$SYSTEMD_DIR"; mkdir -p "$SYSTEMD_DIR"
rm -f "$ETC_DIR/node.env" "$ETC_DIR/blockchain.env"
run_link norole
check "default: escrow-settlements linked"         file_there "$SYSTEMD_DIR/aitbc-escrow-settlements.timer"
check "default: prometheus-watch linked"           file_there "$SYSTEMD_DIR/aitbc-prometheus-watch.service"
check "default: authority-balances NOT linked"     file_gone  "$SYSTEMD_DIR/aitbc-authority-balances.timer"
check "default: hub-only unit not linked"          file_gone  "$SYSTEMD_DIR/aitbc-coordinator-api.service"

echo
if [ "$FAILS" -eq 0 ]; then
    echo "ALL CHECKS PASSED"
else
    echo "$FAILS CHECK(S) FAILED"
    for f in "$SBX"/link-*.out; do echo "--- $f ---"; tail -25 "$f" 2>/dev/null; done
    exit 1
fi
