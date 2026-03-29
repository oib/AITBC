#!/bin/bash
# AITBC Workspace Management Script
# Handles setup, cleanup, and management of external workspaces

set -euo pipefail

# Configuration
WORKSPACE_BASE="/var/lib/aitbc-workspaces"
REPO_URL="http://10.0.3.107:3000/oib/aitbc.git"
GITEA_TOKEN="${GITEA_TOKEN:-b8fbb3e7e6cecf3a01f8a242fc652631c6dfd010}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create workspace base directory
ensure_workspace_base() {
    if [[ ! -d "$WORKSPACE_BASE" ]]; then
        log_info "Creating workspace base directory: $WORKSPACE_BASE"
        sudo mkdir -p "$WORKSPACE_BASE"
        sudo chmod 755 "$WORKSPACE_BASE"
        log_success "Workspace base directory created"
    fi
}

# Setup a specific workspace
setup_workspace() {
    local workspace_type="$1"
    local workspace_dir="$WORKSPACE_BASE/$workspace_type"
    
    log_info "=== Setting up $workspace_type workspace ==="
    
    # Cleanup existing workspace
    if [[ -d "$workspace_dir" ]]; then
        log_warning "Removing existing workspace: $workspace_dir"
        rm -rf "$workspace_dir"
    fi
    
    # Create new workspace
    mkdir -p "$workspace_dir"
    cd "$workspace_dir"
    
    # Clone repository
    log_info "Cloning repository to: $workspace_dir/repo"
    if ! git clone "$REPO_URL" repo; then
        log_error "Failed to clone repository"
        return 1
    fi
    
    cd repo
    log_success "✅ $workspace_type workspace ready at $workspace_dir/repo"
    log_info "Current directory: $(pwd)"
    log_info "Repository contents:"
    ls -la | head -10
    
    # Set git config for CI
    git config --global http.sslVerify false
    git config --global http.postBuffer 1048576000
    
    return 0
}

# Cleanup all workspaces
cleanup_all_workspaces() {
    log_info "=== Cleaning up all workspaces ==="
    
    if [[ -d "$WORKSPACE_BASE" ]]; then
        log_warning "Removing workspace base directory: $WORKSPACE_BASE"
        rm -rf "$WORKSPACE_BASE"
        log_success "All workspaces cleaned up"
    else
        log_info "No workspaces to clean up"
    fi
}

# List all workspaces
list_workspaces() {
    log_info "=== AITBC Workspaces ==="
    
    if [[ ! -d "$WORKSPACE_BASE" ]]; then
        log_info "No workspace base directory found"
        return 0
    fi
    
    log_info "Workspace base: $WORKSPACE_BASE"
    echo
    
    for workspace in "$WORKSPACE_BASE"/*; do
        if [[ -d "$workspace" ]]; then
            local workspace_name=$(basename "$workspace")
            local size=$(du -sh "$workspace" 2>/dev/null | cut -f1)
            local files=$(find "$workspace" -type f 2>/dev/null | wc -l)
            
            echo "📁 $workspace_name"
            echo "   Size: $size"
            echo "   Files: $files"
            echo "   Path: $workspace"
            echo
        fi
    done
}

# Check workspace status
check_workspace() {
    local workspace_type="$1"
    local workspace_dir="$WORKSPACE_BASE/$workspace_type"
    
    log_info "=== Checking $workspace_type workspace ==="
    
    if [[ ! -d "$workspace_dir" ]]; then
        log_warning "Workspace does not exist: $workspace_dir"
        return 1
    fi
    
    if [[ ! -d "$workspace_dir/repo" ]]; then
        log_warning "Repository not found in workspace: $workspace_dir/repo"
        return 1
    fi
    
    cd "$workspace_dir/repo"
    
    local git_status=$(git status --porcelain 2>/dev/null | wc -l)
    local current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    local last_commit=$(git log -1 --format="%h %s" 2>/dev/null || echo "unknown")
    local workspace_size=$(du -sh "$workspace_dir" 2>/dev/null | cut -f1)
    
    echo "📊 Workspace Status:"
    echo "   Path: $workspace_dir/repo"
    echo "   Size: $workspace_size"
    echo "   Branch: $current_branch"
    echo "   Modified files: $git_status"
    echo "   Last commit: $last_commit"
    
    return 0
}

# Main function
main() {
    local command="${1:-help}"
    
    case "$command" in
        "setup")
            ensure_workspace_base
            setup_workspace "${2:-python-packages}"
            ;;
        "cleanup")
            cleanup_all_workspaces
            ;;
        "list")
            list_workspaces
            ;;
        "check")
            check_workspace "${2:-python-packages}"
            ;;
        "help"|*)
            echo "AITBC Workspace Management Script"
            echo
            echo "Usage: $0 <command> [args]"
            echo
            echo "Commands:"
            echo "  setup [workspace]    Setup a workspace (default: python-packages)"
            echo "  cleanup             Clean up all workspaces"
            echo "  list                List all workspaces"
            echo "  check [workspace]   Check workspace status"
            echo "  help                Show this help"
            echo
            echo "Available workspaces:"
            echo "  python-packages"
            echo "  javascript-packages"
            echo "  security-tests"
            echo "  integration-tests"
            echo "  compatibility-tests"
            echo
            echo "Examples:"
            echo "  $0 setup python-packages"
            echo "  $0 setup javascript-packages"
            echo "  $0 check python-packages"
            echo "  $0 list"
            echo "  $0 cleanup"
            ;;
    esac
}

# Run main function
main "$@"
