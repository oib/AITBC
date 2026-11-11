#!/bin/bash
# Secret Rotation Script for API_KEY_HASH_SECRET
# This script rotates API_KEY_HASH_SECRET with zero-downtime using dual-secret
# overlap: coordinator-api derives API-key digests with HMAC under
# API_KEY_HASH_SECRET and also accepts API_KEY_HASH_SECRET_NEW /
# API_KEY_HASH_SECRET_PREVIOUS while a rotation is in flight (see the
# enterprise-integration partners router).
# Usage: sudo ./rotate_api_key_secret.sh < secret.txt
#        (or: NEW_SECRET=... sudo -E ./rotate_api_key_secret.sh)
# The secret is never passed as an argument -- argv is visible via ps and shell history.
#
# #1718: the rotation targets are DISCOVERED, not hardcoded. The secret may
# live in a shared env file (e.g. blockchain-secrets.env) or per-service
# files, and the consuming units are whatever references those files via
# EnvironmentFile=. Writing API_KEY_HASH_SECRET_NEW into env files nothing
# loads — or restarting a stale hardcoded unit list — leaves consumers
# verifying only the old secret while signers move to the new one.

set -euo pipefail

# Configuration
ENV_DIR="${AITBC_ENV_DIR:-/etc/aitbc}"
SYSTEMD_DIR="${AITBC_SYSTEMD_DIR:-/etc/systemd/system}"
LOG_DIR="${AITBC_LOG_DIR:-/var/log/aitbc}"
# Backups and the generated rollback script live in a per-run directory under a
# root-private tree — never a fixed /tmp path, and a concurrent run's backups
# can never be eaten by this run's rollback or cleanup.
BACKUP_ROOT="${AITBC_BACKUP_DIR:-/var/lib/aitbc/secret-rotation}"
SECRET_KEY="API_KEY_HASH_SECRET"
ROLLBACK_FILE=""
LOG_FILE="${LOG_DIR}/api_key_rotation_$(date +%Y%m%d_%H%M%S).log"

# --dry-run prints the rotation plan and exits before any write, restart,
# or log-file creation — a preview must not mutate anything (#1499).
DRY_RUN=false
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        *) break ;;
    esac
done

# Env files under ENV_DIR that actually carry SECRET_KEY=.
discover_env_files() {
    local f
    for f in "$ENV_DIR"/*.env; do
        [ -f "$f" ] || continue
        if grep -q "^${SECRET_KEY}=" "$f"; then
            basename "$f"
        fi
    done
}

# Bare unit names (no .service suffix) that consume an env file: either the
# file is named <unit>.env and <unit>.service exists (systemctl cat also
# sees generated/dropped-in units), or a unit file under SYSTEMD_DIR lists
# the env file in EnvironmentFile= — by path, basename, or a %N specifier
# resolving to <unit>.env / <unit>-override.env.
units_for_env_file() {
    local env_base="$1" cand unit tok resolved uname
    cand="${env_base%.env}"
    # <unit>.env implies <unit>.service; systemctl cat fails for units that
    # do not exist, so a shared file like blockchain-secrets.env cannot
    # spawn a bogus "blockchain-secrets" restart.
    if [ "$cand" != "$env_base" ] && systemctl cat "$cand.service" >/dev/null 2>&1; then
        echo "$cand"
    fi
    for unit in "$SYSTEMD_DIR"/aitbc-*.service "$SYSTEMD_DIR"/aitbc-*.service.d/*.conf; do
        [ -f "$unit" ] || continue
        case "$unit" in
            *.service.d/*.conf)
                uname=$(basename "$(dirname "$unit")" .d)
                uname="${uname%.service}"
                ;;
            *)
                uname=$(basename "$unit" .service)
                ;;
        esac
        while IFS= read -r tok; do
            [ -n "$tok" ] || continue
            resolved="${tok//%N/$uname}"
            case "$resolved" in
                */"$env_base" | "$env_base") echo "$uname" ;;
            esac
        done < <(grep -oE 'EnvironmentFile=-?[^ "'"'"']+' "$unit" 2>/dev/null | sed 's/^EnvironmentFile=-\{0,1\}//')
    done
}

# Union of consuming units across every rotated env file, deduplicated.
discover_units() {
    local env_base u
    for env_base in "${ENV_FILES[@]}"; do
        units_for_env_file "$env_base"
    done | sort -u
}

if [ "$DRY_RUN" = true ]; then
    if [ $# -gt 0 ]; then
        echo "error: unexpected arguments with --dry-run: $*" >&2
        exit 2
    fi
    echo "dry-run: ${SECRET_KEY} rotation plan (no writes, no restarts, no log file)"
    echo "  env dir:      $ENV_DIR"
    echo "  systemd dir:  $SYSTEMD_DIR"
    echo "  backup root:  $BACKUP_ROOT (per-run 0700 dir + rollback.sh)"
    echo "  log file:     $LOG_FILE (not created in dry-run)"
    ENV_FILES=()
    while IFS= read -r f; do ENV_FILES+=("$f"); done < <(discover_env_files)
    found=0
    if [ ${#ENV_FILES[@]} -gt 0 ]; then
        found=1
        UNITS=()
        while IFS= read -r u; do UNITS+=("$u"); done < <(discover_units)
        for env_base in "${ENV_FILES[@]}"; do
            echo "  $env_base: would rewrite $ENV_DIR/$env_base"
        done
        if [ ${#UNITS[@]} -gt 0 ]; then
            echo "  restarts: ${UNITS[*]} (two rolling passes, health-checked)"
        else
            echo "  restarts: none discovered — env files rotate; consumers pick up on next restart"
        fi
    else
        echo "  warning: no env file under $ENV_DIR contains ${SECRET_KEY}= — rotation would be a no-op"
    fi
    echo "  writes:   ${SECRET_KEY}_NEW alongside old → rolling restarts →"
    echo "           ${SECRET_KEY}=new, old retired into ${SECRET_KEY}_PREVIOUS"
    echo "  rollback: per-run rollback.sh restores only this run's backups"
    exit 0
fi

mkdir -p "$LOG_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
    log "${RED}ERROR: $1${NC}"
    if [ -n "$ROLLBACK_FILE" ] && [ -f "$ROLLBACK_FILE" ]; then
        log "Rollback script saved to: $ROLLBACK_FILE"
    fi
    exit 1
}

# Replace KEY=<anything> with KEY=<value> in a file, treating <value> literally.
#
# This was `sed -i "s/KEY=.*/KEY=$NEW_SECRET/"`. Base64 secrets commonly contain `/` and
# `&`, which sed treats as the expression delimiter and "the matched text" respectively,
# so a perfectly valid secret could corrupt the env file or write the wrong value.
set_env_var() {
    local key="$1" value="$2" file="$3"
    KEY="$key" VALUE="$value" FILE="$file" python3 - <<'PY'
import os
import re

key = os.environ["KEY"]
value = os.environ["VALUE"]
path = os.environ["FILE"]

with open(path) as handle:
    lines = handle.readlines()
# A file whose last line lacks a trailing newline would
# otherwise fuse the appended KEY=... onto it and silently lose the var.
if lines and not lines[-1].endswith("\n"):
    lines[-1] += "\n"

pattern = re.compile(rf"^{re.escape(key)}=")
replaced = False
for index, line in enumerate(lines):
    if pattern.match(line):
        lines[index] = f"{key}={value}\n"
        replaced = True

if not replaced:
    lines.append(f"{key}={value}\n")

with open(path, "w") as handle:
    handle.writelines(lines)
PY
}

# Remove a KEY=... line entirely.
unset_env_var() {
    local key="$1" file="$2"
    KEY="$key" FILE="$file" python3 - <<'PY'
import os
import re

key = os.environ["KEY"]
path = os.environ["FILE"]
pattern = re.compile(rf"^{re.escape(key)}=")

with open(path) as handle:
    lines = handle.readlines()
# A file whose last line lacks a trailing newline would
# otherwise fuse the appended KEY=... onto it and silently lose the var.
if lines and not lines[-1].endswith("\n"):
    lines[-1] += "\n"
with open(path, "w") as handle:
    handle.writelines(line for line in lines if not pattern.match(line))
PY
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error_exit "This script must be run as root"
fi

# Read the new secret without exposing it in argv.
#
# Anything passed as a command-line argument is world-readable via `ps aux` and
# /proc/<pid>/cmdline for the lifetime of the process, and is written to the invoking
# shell's history file. Accept the secret on stdin, or via the NEW_SECRET environment
# variable, instead.
if [ -n "${1:-}" ]; then
    error_exit "Refusing to take the secret as an argument (visible in ps/shell history). Pipe it on stdin: $0 < secret.txt"
fi

if [ -n "${NEW_SECRET:-}" ]; then
    log "Reading new secret from NEW_SECRET environment variable"
elif [ ! -t 0 ]; then
    log "Reading new secret from stdin"
    IFS= read -r NEW_SECRET || true
else
    error_exit "Usage: $0 < secret.txt   (or set NEW_SECRET in the environment)"
fi

if [ -z "${NEW_SECRET:-}" ]; then
    error_exit "New secret is empty"
fi
log "Starting ${SECRET_KEY} rotation for rolling release"
log "New secret length: ${#NEW_SECRET} characters"

# Discover targets before any write: env files carrying the key, and the
# units that consume them.
ENV_FILES=()
while IFS= read -r f; do ENV_FILES+=("$f"); done < <(discover_env_files)
if [ ${#ENV_FILES[@]} -eq 0 ]; then
    error_exit "No env file under $ENV_DIR contains ${SECRET_KEY}= — nothing to rotate"
fi
UNITS=()
while IFS= read -r u; do UNITS+=("$u"); done < <(discover_units)
log "Rotating ${#ENV_FILES[@]} env file(s): ${ENV_FILES[*]}"
if [ ${#UNITS[@]} -gt 0 ]; then
    log "Consuming units: ${UNITS[*]}"
else
    log "${YELLOW}No consuming units discovered — env files will rotate; services pick up the new secret on their next restart${NC}"
fi

# Backup current secrets into this run's private directory. The backups hold
# plaintext secrets, so the tree is 0700 throughout.
mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"
RUN_DIR="$(mktemp -d "$BACKUP_ROOT/run.XXXXXXXX")"
chmod 700 "$RUN_DIR"
ROLLBACK_FILE="$RUN_DIR/rollback.sh"
log "Backing up current secrets to $RUN_DIR..."
for env_base in "${ENV_FILES[@]}"; do
    cp "$ENV_DIR/$env_base" "$RUN_DIR/$env_base"
    log "Backed up $env_base"
done

# Create rollback script — restores only this run's backups and nothing else.
UNIT_LIST="${UNITS[*]:-}"
cat > "$ROLLBACK_FILE" << ROLLBACK_EOF
#!/bin/bash
# Auto-generated rollback script for API key secret rotation
set -e
echo "Rolling back API key secret rotation..."
# Restore this run's backups only
for backup in $RUN_DIR/*.env; do
    if [ -f "\$backup" ]; then
        cp "\$backup" "$ENV_DIR/\$(basename "\$backup")"
        echo "Restored \$backup"
    fi
done
# Restart all services
if [ -n "$UNIT_LIST" ]; then
    systemctl restart $UNIT_LIST
else
    echo "No consuming units were discovered; restart services manually to restore the old secret."
fi
echo "Rollback complete"
ROLLBACK_EOF
chmod 700 "$ROLLBACK_FILE"
log "Rollback script created: $ROLLBACK_FILE"

restart_units() {
    local u
    for u in "${UNITS[@]}"; do
        [ -n "$u" ] || continue
        log "Restarting $u..."
        systemctl restart "$u"
        log "Waiting for $u to be healthy..."
        sleep 10
        if systemctl is-active --quiet "$u"; then
            log "${GREEN}$u is healthy${NC}"
        else
            error_exit "$u failed to start"
        fi
    done
}

# Phase 1: Add new secret alongside old secret (dual-secret overlap)
log "Phase 1: Adding new secret with dual-secret overlap..."
for env_base in "${ENV_FILES[@]}"; do
    env_file="$ENV_DIR/$env_base"
    # Add new secret as API_KEY_HASH_SECRET_NEW (set_env_var appends safely even when
    # the file lacks a trailing newline — a bare `echo >>` would fuse
    # the assignment onto the last line and lose the variable).
    set_env_var "${SECRET_KEY}_NEW" "$NEW_SECRET" "$env_file"
    log "Set ${SECRET_KEY}_NEW in $env_base"
done

# Phase 2: Rolling restart services one by one. A restarted service signs
# with the OLD secret and verifies {old, new}; a not-yet-restarted one keeps
# its phase-1 env — API_KEY_HASH_SECRET_NEW stays in its process environment
# until its own restart, so new-secret digests still verify there. Both
# directions of the overlap hold for the whole pass.
log "Phase 2: Rolling restart services with dual-secret support..."
if [ ${#UNITS[@]} -gt 0 ]; then
    restart_units
else
    log "${YELLOW}No units to restart — skipping rolling restart${NC}"
fi

# Phase 3: Verify all services are healthy with dual-secret support
log "Phase 3: Verifying all services are healthy..."
for u in "${UNITS[@]}"; do
    if systemctl is-active --quiet "$u"; then
        log "${GREEN}$u is healthy${NC}"
    else
        error_exit "$u is not healthy after dual-secret phase"
    fi
done

# Phase 4: Replace old secret with new secret.
# The retired secret is moved to API_KEY_HASH_SECRET_PREVIOUS (comma-separated
# with any earlier retirees): stored credential digests are keyed by the secret
# that was live when they were issued, so the old secret must keep verifying
# them — that is what makes the overlap real.
log "Phase 4: Replacing old secret with new secret..."
for env_base in "${ENV_FILES[@]}"; do
    env_file="$ENV_DIR/$env_base"
    old_secret="$(sed -n "s/^${SECRET_KEY}=//p" "$env_file" | head -n1)"
    previous="$(sed -n "s/^${SECRET_KEY}_PREVIOUS=//p" "$env_file" | head -n1)"
    # Replace API_KEY_HASH_SECRET with the new secret
    set_env_var "$SECRET_KEY" "$NEW_SECRET" "$env_file"
    # Move API_KEY_HASH_SECRET_NEW into the retired-secret slot
    unset_env_var "${SECRET_KEY}_NEW" "$env_file"
    if [ -n "$old_secret" ]; then
        if [ -n "$previous" ]; then
            previous="$old_secret,$previous"
        else
            previous="$old_secret"
        fi
        set_env_var "${SECRET_KEY}_PREVIOUS" "$previous" "$env_file"
    fi
    log "Updated $env_base with new secret (old retained in ${SECRET_KEY}_PREVIOUS)"
done

# Phase 5: Final rolling restart with new secret signing.
# Not-yet-restarted services still verify {old, new} via the *_SECRET_NEW in
# their phase-2 process environment; restarted ones verify {new, old} via
# *_SECRET_PREVIOUS. *_SECRET_PREVIOUS stays until every credential issued
# under the retired secret has expired.
log "Phase 5: Final rolling restart with new secret signing..."
if [ ${#UNITS[@]} -gt 0 ]; then
    restart_units
else
    log "${YELLOW}No units to restart — skipping final rolling restart${NC}"
fi

# Phase 6: Final verification
log "Phase 6: Final verification..."
for u in "${UNITS[@]}"; do
    if systemctl is-active --quiet "$u"; then
        log "${GREEN}$u is healthy${NC}"
    else
        error_exit "$u is not healthy after final restart"
    fi
done

# Cleanup
log "Cleaning up this run's backup files..."
# Backups contain the OLD PLAINTEXT SECRET. Rotation has completed and every
# service has been verified healthy, so this run's directory is removed now —
# only this run's; any other run's backups under $BACKUP_ROOT are untouched.
rm -rf "$RUN_DIR"
log "Rollback script and run backups removed"

log "${GREEN}${SECRET_KEY} rotation completed successfully${NC}"
log "Rotation log saved to: $LOG_FILE"
