#!/usr/bin/env bash
set -euo pipefail

# Stop all AITBC services

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
                kill "$PID"
            fi
        fi
    done
    if [ "$DRY_RUN" = false ]; then
        rm -f .service_pids
    else
        echo "[DRY RUN] Would remove .service_pids file"
    fi
fi

# Force kill any remaining services
echo "Cleaning up any remaining processes..."
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would run: sudo fuser -k 8000/tcp"
    echo "[DRY RUN] Would run: sudo fuser -k 9080/tcp"
    echo "[DRY RUN] Would run: sudo fuser -k 3001/tcp"
    echo "[DRY RUN] Would run: sudo fuser -k 3002/tcp"
    echo "[DRY RUN] Would run: pkill -f 'uvicorn.*aitbc'"
    echo "[DRY RUN] Would run: pkill -f 'server.py'"
else
    if [ "$FORCE" = false ]; then
        echo "⚠️  This will forcefully kill processes on ports 8000, 9080, 3001, 3002"
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "❌ Aborted"
            exit 1
        fi
    fi
    sudo fuser -k 8000/tcp 2>/dev/null || true
    sudo fuser -k 9080/tcp 2>/dev/null || true
    sudo fuser -k 3001/tcp 2>/dev/null || true
    sudo fuser -k 3002/tcp 2>/dev/null || true
    pkill -f "uvicorn.*aitbc" 2>/dev/null || true
    pkill -f "server.py" 2>/dev/null || true
fi

if [ "$DRY_RUN" = true ]; then
    echo "🔍 DRY RUN COMPLETE - No changes were made"
else
    echo "✅ All services stopped!"
fi
