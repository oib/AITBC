#!/usr/bin/env bash
set -euo pipefail

# Stop all AITBC services

# Service list and ports come from lib/services.sh so all of these scripts agree.
source "$(dirname "${BASH_SOURCE[0]}")/lib/services.sh"

DRY_RUN=false
FORCE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --yes)
            FORCE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--dry-run] [--yes]"
            echo "  --dry-run  Show what would be done without executing"
            echo "  --yes      Skip confirmation prompt"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "🛑 Stopping AITBC Services"
echo "========================"

STOP_FAILED=0

if [ "$DRY_RUN" = true ]; then
    echo "🔍 DRY RUN MODE - No changes will be made"
    echo ""
fi

# Stop by PID if file exists
if [ -f .service_pids ]; then
    PIDS=$(cat .service_pids)
    echo "Found PIDs: $PIDS"
    for PID in $PIDS; do
        if kill -0 "$PID" 2>/dev/null; then
            if [ "$DRY_RUN" = true ]; then
                echo "[DRY RUN] Would stop PID $PID..."
            else
                echo "Stopping PID $PID..."
                kill "$PID" || { echo "   failed to stop PID $PID"; STOP_FAILED=1; }
            fi
        fi
    done
    if [ "$DRY_RUN" = false ]; then
        rm -f .service_pids
    else
        echo "[DRY RUN] Would remove .service_pids file"
    fi
fi

# Stop the systemd units, in reverse startup order (dependents first).
echo "Stopping systemd services..."
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would run: sudo systemctl stop $(aitbc_services_reversed | tr '\n' ' ')"
else
    if [ "$FORCE" = false ]; then
        echo "⚠️  This will stop all AITBC systemd services"
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "❌ Aborted"
            exit 1
        fi
    fi
    while read -r svc; do
        sudo -n systemctl stop "$svc" 2>/dev/null || { echo "   systemctl stop failed: $svc"; STOP_FAILED=1; }
    done < <(aitbc_services_reversed)
    # Verify: a unit that is still active after stop is a failure, not a
    # stray process to fuser -k away.
    while read -r svc; do
        if systemctl is-active --quiet "$svc"; then
            echo "   still active after stop: $svc"
            STOP_FAILED=1
        fi
    done < <(aitbc_services_reversed)
fi

if [ "$DRY_RUN" = true ]; then
    echo "🔍 DRY RUN COMPLETE - No changes were made"
elif [ "$STOP_FAILED" -eq 0 ]; then
    echo "✅ All services stopped!"
else
    echo "❌ Some services did not stop cleanly"
    exit 1
fi
