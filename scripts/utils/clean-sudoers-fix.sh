#!/bin/bash
#
# Clean AITBC Sudoers - argument-fixed service commands only.
#
# The old version of this file granted NOPASSWD root for recursive
# chown/chmod over arbitrary paths, bare wildcard git/make/gcc/pip commands,
# recursive rm under /opt/aitbc and a runas-everything grant. A sudoers *
# matches spaces and slashes, so each of those was a full root equivalent
# presented as a minimal config. It also wrote
# the file straight into /etc/sudoers.d before running visudo -c, leaving a
# broken sudoers in place on a syntax error.
#
# This version writes a temp file, validates it with visudo -cf, and only
# then installs it. Grants are pinned to argument-fixed commands; anything
# broader needs a root shell, deliberately.

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

SUDOERS_DIR="${AITBC_SUDOERS_DIR:-/etc/sudoers.d}"
SUDOERS_NAME="aitbc-dev"

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Write the sudoers candidate to a temp file (NOT into sudoers.d).
write_sudoers_candidate() {
    tmp_sudoers="$(mktemp "${TMPDIR:-/tmp}/aitbc-sudoers.XXXXXX")"
    chmod 440 "$tmp_sudoers"

    cat > "$tmp_sudoers" << 'EOF'
# AITBC Development Sudoers Configuration
# Argument-fixed commands only — anything broader is a root equivalent and
# must go through a root shell, not a wildcard grant.

# Service management (one alias per verb keeps the unit wildcard pinned to a
# single argument position; it cannot smuggle a second command)
oib ALL=(root) NOPASSWD: /usr/bin/systemctl start aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl stop aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl restart aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl status aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl is-active aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/systemctl daemon-reload

# Log access
oib ALL=(root) NOPASSWD: /usr/bin/journalctl -u aitbc-*
oib ALL=(root) NOPASSWD: /usr/bin/journalctl -u aitbc-* --no-pager
EOF

    printf '%s\n' "$tmp_sudoers"
}

# Validate a candidate file, install it into sudoers.d only on success.
validate_and_install() {
    local tmp_sudoers="$1"
    local target="$SUDOERS_DIR/$SUDOERS_NAME"

    print_header "Validating Sudoers Candidate"
    if ! visudo -c -f "$tmp_sudoers"; then
        print_error "Sudoers syntax check failed — nothing installed"
        rm -f "$tmp_sudoers"
        return 1
    fi
    print_status "Sudoers syntax is valid"

    install -m 0440 -o root -g root "$tmp_sudoers" "$target"
    rm -f "$tmp_sudoers"
    print_status "Installed: $target"
}

main() {
    print_header "Clean AITBC Sudoers Fix"
    echo "Creating argument-fixed sudoers configuration"
    echo ""

    if [[ $EUID -ne 0 && -z "${AITBC_SUDOERS_DIR:-}" ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi

    mkdir -p "$SUDOERS_DIR"
    tmp_sudoers="$(write_sudoers_candidate)"

    if validate_and_install "$tmp_sudoers"; then
        print_header "Success"
        echo "Grant list: systemctl {start,stop,restart,status,is-active} aitbc-*,"
        echo "systemctl daemon-reload, journalctl -u aitbc-*"
        echo ""
        echo "For everything else (chown/chmod/git/pip/etc.) use a root shell —"
        echo "a wildcard grant is root anyway, minus the audit trail."
    else
        exit 1
    fi
}

main "$@"
