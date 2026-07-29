#!/usr/bin/env bash
# =============================================================================
# backend-prune-instances.sh — delete seat_spawn junk rows by instance_id
# (PILOT-46 / ABS-546)
# =============================================================================
# Replaces the operator's manual psql surgery after a sandbox-env leak floods
# the Mission Control board with seat_spawn rows from throwaway instances
# (devops01.local-<pid>-<hash>, test-instance-*). Table: seat_spawn (migration
# 013/019).
#
# SAFE BY DEFAULT: dry-run. It ALWAYS writes a CSV backup of the matching rows
# first, prints how many rows match, and deletes NOTHING unless you pass
# --apply. The instance_id match is a POSIX regex (Postgres `~`), passed as a
# bound psql variable (never string-concatenated into SQL).
#
# Usage:
#   scripts/backend-prune-instances.sh --pattern '<regex>' [options]
#
# Options:
#   --pattern <regex>     REQUIRED. POSIX regex matched against instance_id,
#                         e.g. '^devops01\.local-' or '^test-instance-'.
#   --apply               Actually DELETE (default is dry-run — no delete).
#   --database-url <url>  Postgres URL (default: $DATABASE_URL).
#   --backup-dir <dir>    Where to write the CSV backup (default: current dir).
#   -h, --help            Show this help.
#
# Exit 0 = ok (dry-run reported, or rows deleted). Exit 2 = usage/setup error.
# =============================================================================

set -euo pipefail

PATTERN=""
APPLY=0
DB_URL="${DATABASE_URL:-}"
BACKUP_DIR="."
PSQL="${PSQL:-psql}"

# Print the leading comment block (help text), stripping the "# " prefix and the
# ==== border rules, up to the first non-comment line.
usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,""); if ($0 ~ /^=+$/) next; print; next} {exit}' "$0"; }

die() { printf 'backend-prune-instances: %s\n' "$1" >&2; exit 2; }

while [ "$#" -gt 0 ]; do
    case "$1" in
        --pattern)      PATTERN="${2:-}"; shift 2 ;;
        --apply)        APPLY=1; shift ;;
        --database-url) DB_URL="${2:-}"; shift 2 ;;
        --backup-dir)   BACKUP_DIR="${2:-}"; shift 2 ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "unknown argument: $1" ;;
    esac
done

[ -n "$PATTERN" ] || die "--pattern <regex> is required (nothing matched, nothing deleted)"
[ -n "$DB_URL" ]  || die "no database URL: pass --database-url or set DATABASE_URL"
[ -d "$BACKUP_DIR" ] || die "backup dir does not exist: $BACKUP_DIR"

ts="$(date +%Y%m%dT%H%M%SZ)"
backup="$BACKUP_DIR/seat_spawn-prune-$ts.csv"

# psql performs :'pat' variable interpolation ONLY for SQL read from stdin (or
# -f); with -c it sends the string verbatim to the server, so :'pat' reaches
# Postgres unsubstituted and every call dies with "syntax error at or near :".
# That is why this tool never worked against a real database. Feed each SQL on
# stdin so the bound-variable substitution actually happens (the pattern is
# still a bound psql variable, never concatenated into SQL). ON_ERROR_STOP=1
# makes psql exit non-zero on any SQL error so `set -euo pipefail` aborts —
# critically, a FAILED backup must never fall through to a DELETE.
PV=(-X -v ON_ERROR_STOP=1 -v pat="$PATTERN")

# --- count matching rows -----------------------------------------------------
count="$(printf "SELECT count(*) FROM seat_spawn WHERE instance_id ~ :'pat'\n" \
    | "$PSQL" "$DB_URL" -A -t "${PV[@]}" | tr -d '[:space:]')"
count="${count:-0}"

printf 'backend-prune-instances: %s row(s) match instance_id ~ %s\n' "$count" "$PATTERN"

# --- always write a CSV backup of the matching rows --------------------------
# COPY … TO STDOUT is a plain SQL command (interpolates :'pat' via stdin, unlike
# the \copy meta-command), streamed to the backup file client-side.
printf "COPY (SELECT * FROM seat_spawn WHERE instance_id ~ :'pat') TO STDOUT WITH CSV HEADER\n" \
    | "$PSQL" "$DB_URL" -A -t "${PV[@]}" > "$backup"
printf 'backend-prune-instances: CSV backup written to %s\n' "$backup"

if [ "$APPLY" -ne 1 ]; then
    printf 'backend-prune-instances: DRY-RUN — no rows deleted. Re-run with --apply to delete.\n'
    exit 0
fi

# --- delete ------------------------------------------------------------------
printf "DELETE FROM seat_spawn WHERE instance_id ~ :'pat'\n" \
    | "$PSQL" "$DB_URL" -q "${PV[@]}"
printf 'backend-prune-instances: DELETED %s row(s) matching %s (backup: %s)\n' \
    "$count" "$PATTERN" "$backup"
exit 0
