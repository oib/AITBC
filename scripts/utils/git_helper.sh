#!/bin/bash
# AITBC Git Workflow Helper Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="/opt/aitbc"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if we're in the git repo
check_git_repo() {
    if [ ! -d "$REPO_DIR/.git" ]; then
        print_error "Git repository not found at $REPO_DIR"
        exit 1
    fi
}

# Function to show git status
show_status() {
    print_status "Git Repository Status:"
    cd "$REPO_DIR"
    sudo -u aitbc git status
}

# Function to commit changes (excluding sensitive files)
commit_changes() {
    local message="$1"
    if [ -z "$message" ]; then
        print_error "Commit message is required"
        exit 1
    fi
    
    print_status "Committing changes with message: $message"
    cd "$REPO_DIR"
    
    # Add only tracked files (avoid adding sensitive data)
    sudo -u aitbc git add -u
    sudo -u aitbc git commit -m "$message"
    
    print_status "Changes committed successfully"
}

# Function to create a backup branch
backup_branch() {
    local branch_name="backup-$(date +%Y%m%d-%H%M%S)"
    print_status "Creating backup branch: $branch_name"
    cd "$REPO_DIR"
    sudo -u aitbc git checkout -b "$branch_name"
    sudo -u aitbc git checkout main
    print_status "Backup branch created: $branch_name"
}

# Function to show recent commits
show_history() {
    local count="${1:-10}"
    print_status "Recent $count commits:"
    cd "$REPO_DIR"
    sudo -u aitbc git log --oneline -n "$count"
}

# Function to clean up untracked files
cleanup() {
    print_status "Cleaning up untracked files..."
    cd "$REPO_DIR"
    sudo -u aitbc git clean -fd
    print_status "Cleanup completed"
}

# Function to sync with remote
sync_remote() {
    print_status "Syncing with remote repository..."
    cd "$REPO_DIR"
    sudo -u aitbc git fetch origin
    sudo -u aitbc git pull origin main
    print_status "Sync completed"
}

# Function to push to remote
push_remote() {
    print_status "Pushing to remote repository..."
    cd "$REPO_DIR"
    sudo -u aitbc git push origin main
    print_status "Push completed"
}

# Main function
main() {
    case "${1:-help}" in
        "status")
            check_git_repo
            show_status
            ;;
        "commit")
            check_git_repo
            commit_changes "$2"
            ;;
        "backup")
            check_git_repo
            backup_branch
            ;;
        "history")
            check_git_repo
            show_history "$2"
            ;;
        "cleanup")
            check_git_repo
            cleanup
            ;;
        "sync")
            check_git_repo
            sync_remote
            ;;
        "push")
            check_git_repo
            push_remote
            ;;
        "help"|*)
            echo "AITBC Git Workflow Helper"
            echo ""
            echo "Usage: $0 {status|commit|backup|history|cleanup|sync|push|help}"
            echo ""
            echo "Commands:"
            echo "  status           - Show git repository status"
            echo "  commit <msg>    - Commit changes with message"
            echo "  backup           - Create backup branch with timestamp"
            echo "  history [count]  - Show recent commits (default: 10)"
            echo "  cleanup          - Clean up untracked files"
            echo "  sync             - Sync with remote repository"
            echo "  push             - Push to remote repository"
            echo "  help             - Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 status"
            echo "  $0 commit \"Updated service configuration\""
            echo "  $0 backup"
            echo "  $0 history 5"
            echo "  $0 sync"
            echo "  $0 push"
            ;;
    esac
}

main "$@"