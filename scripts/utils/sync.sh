#!/bin/bash
# AITBC repository sync.
#
# Topology -- the flow is one-directional, and only one host mirrors:
#
#     gitea.bubuit.net/oib/AITBC  (origin, canonical)
#              |                     ^
#         pull |                     | push (mirror only)
#              v                     |
#     nodes: /opt/aitbc        IDE host: /opt/aitbc
#     (origin remote only)     (origin + github remote)
#                                     |
#                                     v
#                        github.com/oib/AITBC  (mirror, read-only downstream)
#
# Nodes pull from gitea and never push anywhere; they hold no GitHub
# credentials. The IDE host is the only place with a github push URL, and it
# mirrors what gitea already has rather than pushing local work straight to
# GitHub.
#
# Usage: ./sync.sh [status|pull|mirror|deploy]

set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

BRANCH=${SYNC_BRANCH:-main}
ACTION=${1:-status}

# Whether this host can mirror is a property of its git config, not its name.
# The previous version gated on `hostname = "aitbc"`, which matches no host in
# the fleet -- so its "don't push from production" guard never fired and its
# deploy guard always blocked. Ask the remote instead.
github_push_url() {
    git remote get-url --push github 2>/dev/null || true
}

can_mirror() {
    local url
    url=$(github_push_url)
    [ -n "$url" ] && [ "$url" != "no_push" ]
}

require_clean_tree() {
    if [ -n "$(git status --porcelain)" ]; then
        echo "Working tree is not clean; refusing to $1." >&2
        git status --short >&2
        exit 1
    fi
}

echo "=== AITBC sync ==="
echo "Host:   $(hostname)"
echo "Repo:   $REPO_ROOT"
echo "Branch: $BRANCH"
echo "Action: $ACTION"
echo

case "$ACTION" in
    status)
        echo "Remotes:"
        git remote -v
        echo
        echo "Mirror capability: $(can_mirror && echo "yes ($(github_push_url))" || echo "no -- pull-only host")"
        echo
        git fetch --quiet origin "$BRANCH" || echo "(could not reach origin)"
        echo "Local vs origin/$BRANCH:"
        git rev-list --left-right --count "HEAD...origin/$BRANCH" 2>/dev/null \
            | awk '{print "  ahead " $1 ", behind " $2}' || echo "  (unknown)"
        echo
        echo "Recent commits:"
        git log --oneline -3
        ;;

    pull)
        require_clean_tree "pull"
        echo "Pulling $BRANCH from origin (gitea)..."
        git fetch origin "$BRANCH"
        # Fast-forward only: a node that cannot fast-forward has diverged, and
        # silently merging or rebasing production checkouts hides that.
        git merge --ff-only "origin/$BRANCH"
        # Contracts' forge-std/openzeppelin deps are submodules; fetch them only
        # on hosts that can build contracts (foundry installed). No-op elsewhere.
        if [ -f .gitmodules ] && command -v forge >/dev/null 2>&1; then
            git submodule update --init --recursive || echo "warning: submodule update failed" >&2
        fi
        echo "Now at: $(git log --oneline -1)"
        ;;

    mirror)
        if ! can_mirror; then
            echo "This host has no github push URL; mirroring runs from the IDE host only." >&2
            exit 1
        fi
        echo "Mirroring origin/$BRANCH to github..."
        # Push what gitea has, not what happens to be checked out here, so the
        # mirror can never carry commits gitea has not accepted.
        git fetch origin "$BRANCH"
        git push github "origin/$BRANCH:refs/heads/$BRANCH"
        echo "github/$BRANCH now at: $(git rev-parse --short "origin/$BRANCH")"
        ;;

    push)
        echo "'push' is now 'mirror' (and no longer auto-commits). Running mirror..." >&2
        exec "$0" mirror
        ;;

    deploy)
        require_clean_tree "deploy"
        echo "Deploying $BRANCH from origin (gitea)..."
        git fetch origin "$BRANCH"
        git merge --ff-only "origin/$BRANCH"
        "$REPO_ROOT/scripts/utils/manage-services.sh" restart
        echo "Deployed: $(git log --oneline -1)"
        ;;

    *)
        echo "Usage: $0 [status|pull|mirror|deploy]"
        echo "  status  - remotes, mirror capability, divergence from origin"
        echo "  pull    - fast-forward this checkout from gitea"
        echo "  mirror  - push origin/$BRANCH to GitHub (IDE host only)"
        echo "  deploy  - pull, then restart AITBC services"
        exit 1
        ;;
esac
