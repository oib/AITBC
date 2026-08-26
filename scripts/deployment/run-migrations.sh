#!/bin/bash
# ============================================================================
# AITBC — run Alembic migrations for every service that has them
# ----------------------------------------------------------------------------
# The single implementation of "migrate every service safely". `update.sh` runs it as its
# step 5 and `deploy.sh` runs it before starting services for the first time.
#
# It used to live inside `update.sh` alone, which meant a first install never migrated at
# all: `deploy.sh` went initialize_databases -> setup_systemd_services -> start_services and
# brought every service up against whatever schema happened to exist. Extracting it also
# gives an operator something to run on its own, which is how the deployed databases get
# brought to head without a full update (V23-79).
#
# For each apps/*/alembic.ini, in path order:
#   - skip the service if its unit is not linked for this node's role
#   - read DATABASE_URL from that service's own /etc/aitbc/aitbc-<svc>.env
#   - stop the service, `alembic upgrade head`, start it again if it was running
#
# blockchain-node is skipped unless DATABASE_URL is given. It keeps one database per island
# under /var/lib/aitbc/data/<island>/chain.db, and its Alembic default is settings.db_path
# — /var/lib/aitbc/data/chain.db — which no running node uses. A bare `upgrade head` there
# migrates an empty file and reports success; that is exactly what had happened, with the
# default target sitting at head with zero rows while the live island database had no
# alembic_version table at all (V23-49).
#
# Usage:
#   sudo /opt/aitbc/scripts/deployment/run-migrations.sh
#   sudo AITBC_ROOT=/opt/aitbc /opt/aitbc/scripts/deployment/run-migrations.sh
#
# Exit status: 0 if every service migrated or was skipped, 1 if any failed. Callers are
# expected to treat a non-zero exit as "do not restart services with an unknown schema".
# ============================================================================

set -euo pipefail

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
VENV_DIR="${VENV_DIR:-$AITBC_ROOT/venv}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Same four names and the same non-fatal `error` as update.sh: this counts failures per
# service and reports them at the end rather than aborting on the first one.
log()     { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $*"; }
success() { echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓${NC} $*"; }
warning() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠${NC} $*" >&2; }
error()   { echo -e "${RED}[$(date +'%H:%M:%S')] ✗${NC} $*" >&2; }

# Record warnings/errors for an end-of-run agent follow-up block.
__mig_agent_followup_path="$AITBC_ROOT/scripts/utils/agent_followup.sh"
if [ -f "$__mig_agent_followup_path" ]; then
    # shellcheck disable=SC1090
    source "$__mig_agent_followup_path"
    agent_followup_init

    __mig_warning() {
        agent_record_warning "$*"
        echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠${NC} $*" >&2
    }
    __mig_error() {
        agent_record_error "$*"
        echo -e "${RED}[$(date +'%H:%M:%S')] ✗${NC} $*" >&2
    }
    warning() { __mig_warning "$@"; }
    error()   { __mig_error "$@"; }
fi

run_migrations() {
    local alembic_bin="$VENV_DIR/bin/alembic"
    if [ ! -x "$alembic_bin" ]; then
        warning "alembic not found in venv ($alembic_bin) — skipping migrations"
        return 0
    fi

    local migrated=0 failed=0 skipped=0

    # Include repo root, service src, and local py-package src trees so Alembic
    # env.py files can import both aitbc and the aitbc_* helper packages.
    local packages_src
    packages_src=$(find "$AITBC_ROOT/packages/py" -maxdepth 2 -type d -name src 2>/dev/null | tr '\n' ':' || true)
    packages_src="${packages_src%:}"

    while IFS= read -r ini; do
        local svc_dir svc_name unit_file
        svc_dir=$(dirname "$ini")
        svc_name=$(basename "$svc_dir")
        unit_file="/etc/systemd/system/aitbc-${svc_name}.service"

        # Skip services not linked for this node's role (e.g. pool-hub on hub)
        if [ ! -e "$unit_file" ]; then
            log "  skipping $svc_name (not linked for this role)"
            skipped=$((skipped + 1))
            continue
        fi

        log "  Migrating: $svc_name (in $svc_dir)"

        # Locate this service's env file, which carries its DATABASE_URL.
        #
        # The installed files are /etc/aitbc/aitbc-<svc>.env -- the same `aitbc-` prefix the
        # unit-file check three lines above already uses. This looked for <svc>.env without
        # the prefix and so found nothing for blockchain-node, gpu, edge or coordinator-api;
        # pool-hub was the only one that worked, and only because it happens to have a file
        # under both names. The visible effect was coordinator-api migrating its *default*
        # sqlite path while its env file pointed DATABASE_URL at production Postgres.
        local env_file="" candidate
        for candidate in "/etc/aitbc/aitbc-${svc_name}.env" "/etc/aitbc/${svc_name}.env"; do
            if [ -f "$candidate" ]; then
                env_file="$candidate"
                log "    env: $env_file"
                break
            fi
        done

        # Read DATABASE_URL out in a subshell. It must NOT be sourced into this shell: these
        # files export a per-service DATABASE_URL, and one leaking into the next iteration
        # would point that service's `upgrade head` at another service's database. Sourcing
        # coordinator-api's Postgres URL and then migrating edge, gpu, pool-hub and trading
        # into it is a far worse failure than the missing-file bug this replaced.
        local svc_db_url=""
        if [ -n "$env_file" ]; then
            svc_db_url=$(
                unset DATABASE_URL SQLITE_URL
                set +u
                set -a
                # shellcheck disable=SC1090
                source "$env_file" 2>/dev/null || true
                set +a
                printf '%s' "${DATABASE_URL:-}"
            )
        fi

        local pythonpath="$AITBC_ROOT:${svc_dir}/src"
        [ -n "$packages_src" ] && pythonpath="${pythonpath}:${packages_src}"

        # See the header: blockchain-node's Alembic default is a database no node uses, so
        # this refuses to guess which island was meant.
        if [ "$svc_name" = "blockchain-node" ] && [ -z "$svc_db_url" ]; then
            warning "  skipping $svc_name: no DATABASE_URL set, and its default target is not"
            warning "  a database any node uses. Migrate each island explicitly, with the"
            warning "  service stopped:"
            local island_db
            for island_db in /var/lib/aitbc/data/*/chain.db; do
                [ -e "$island_db" ] || continue
                warning "    DATABASE_URL=sqlite:///$island_db \\"
                warning "      $alembic_bin -c $svc_dir/alembic.ini upgrade head"
            done
            skipped=$((skipped + 1))
            continue
        fi

        # Stop the service before touching its schema. SQLite migrations that convert a
        # column go through batch_alter_table(recreate="always"), which drops and rebuilds
        # the table; doing that under a process that holds the file open and has the old
        # schema cached is how a routine update corrupts a live service. Restarted below
        # only if it was running when we arrived -- the caller restarts everything anyway.
        local was_active=false
        if systemctl is-active --quiet "aitbc-${svc_name}"; then
            was_active=true
            log "    stopping aitbc-${svc_name} for the duration of the migration"
            systemctl stop "aitbc-${svc_name}" || true
        fi

        # The env file is sourced *inside* this subshell, so nothing it sets outlives the
        # service it belongs to.
        if (
            set -o pipefail
            unset DATABASE_URL SQLITE_URL
            if [ -n "$env_file" ]; then
                set +u
                set -a
                # shellcheck disable=SC1090
                source "$env_file" 2>/dev/null || true
                set +a
                set -u
            fi
            cd "$svc_dir" && PYTHONPATH="$pythonpath" "$alembic_bin" upgrade head 2>&1 | sed 's/^/    /' && {
                case "${DATABASE_URL:-}" in
                    postgresql*|postgres*)
                        if ! head_check=$(PYTHONPATH="$pythonpath" DATABASE_URL="$DATABASE_URL" "$alembic_bin" -c "$ini" current 2>&1); then
                            echo "Postgres head check for $svc_name failed: $head_check" >&2
                            exit 1
                        fi
                        if ! grep -q '(head)' <<< "$head_check"; then
                            echo "Postgres DB for $svc_name is not at alembic head: $head_check" >&2
                            exit 1
                        fi
                        ;;
                esac
            }
        ); then
            success "  migrated: $svc_name"
            migrated=$((migrated + 1))
            if [ "$was_active" = "true" ]; then
                systemctl start "aitbc-${svc_name}" || true
            fi
        else
            if [ "$was_active" = "true" ]; then
                systemctl start "aitbc-${svc_name}" || true
            fi
            error "  migration failed for $svc_name (multiple heads, missing baseline, or DB unreachable)"
            error "  inspect: cd $svc_dir && PYTHONPATH=$pythonpath $alembic_bin upgrade head"
            failed=$((failed + 1))
        fi
    done < <(find "$AITBC_ROOT/apps" -maxdepth 3 -name "alembic.ini" 2>/dev/null | sort)

    log "Migrations: ${migrated} ok, ${failed} failed, ${skipped} skipped"
    if [ "$failed" -gt 0 ]; then
        error "Migrations failed — not restarting services with an unknown schema"
        return 1
    fi
    return 0
}

verify_schemas() {
    log "Step 5b: Verifying live DB schemas against code models..."
    local script="$AITBC_ROOT/scripts/utils/verify-db-schema.py"
    if [ ! -f "$script" ]; then
        warning "Schema verification script not found: $script"
        return 0
    fi

    local verify_out
    if ! verify_out=$(PYTHONPATH="$AITBC_ROOT" "$VENV_DIR/bin/python" "$script" --all 2>&1); then
        error "DB schema verification failed:"
        echo "$verify_out" | sed 's/^/    /' >&2
        error "Run '$script --all --repair' to add missing nullable columns"
        return 1
    fi

    success "DB schema verification passed"
    if [ -n "$verify_out" ]; then
        echo "$verify_out" | sed 's/^/    /'
    fi
    return 0
}

main() {
    local exit_code=0
    run_migrations || exit_code=$?
    if [ "$exit_code" -eq 0 ]; then
        verify_schemas || exit_code=$?
    fi
    agent_print_followup
    return $exit_code
}

main "$@"
