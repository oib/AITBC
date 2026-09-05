#!/bin/bash
# Install AITBC Python dependencies from poetry.lock based on a hardware/profile.
# Mirrors the profile names used by setup.sh / update.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POETRY_VENV="$REPO_ROOT/venv-poetry"
POETRY="$POETRY_VENV/bin/poetry"
PROFILE="${1:-hub}"

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# shellcheck disable=SC1091
source "$REPO_ROOT/venv/bin/activate"

cd "$REPO_ROOT"

# Load the agent follow-up helper; record failures so the parent script/agent can investigate.
__install_agent_followup_path="$REPO_ROOT/scripts/utils/agent_followup.sh"
if [ -f "$__install_agent_followup_path" ]; then
    # shellcheck disable=SC1090
    source "$__install_agent_followup_path"
    agent_followup_init

    __install_warning() {
        agent_record_warning "$*"
        echo -e "${YELLOW}[WARNING]${NC} $*" >&2
    }
    __install_error() {
        agent_record_error "$*"
        agent_print_followup
        echo -e "${RED}[ERROR]${NC} $*" >&2
        exit 1
    }
    warning() { __install_warning "$@"; }
    error()   { __install_error "$@"; }

    __install_err_trap() {
        local exit_code=$?
        # Do not record a generic error if the script already exited intentionally.
        # EXIT trap will take care of printing.
        if [ -n "${AITBC_AGENT_FOLLOWUP_PRINTED:-}" ]; then
            return
        fi
        agent_record_error "install-profiles.sh command failed: $BASH_COMMAND (exit $exit_code)"
    }
    trap '__install_err_trap' ERR
    trap 'agent_print_followup' EXIT
fi

case "$PROFILE" in
    provider-gpu|gpu)
        EXTRAS="gpu ml"
        ;;
    ai|ml)
        EXTRAS="ml"
        ;;
    fhe)
        EXTRAS="fhe"
        ;;
    hub|customer-no-gpu|server-no-gpu|default)
        EXTRAS=""
        ;;
    *)
        warning "Unknown profile '$PROFILE', falling back to base dependencies"
        EXTRAS=""
        ;;
esac

if [ ! -x "$POETRY" ]; then
    echo "Bootstrapping Poetry into $POETRY_VENV ..."
    python3 -m venv "$POETRY_VENV"
    "$POETRY_VENV/bin/pip" install -q "poetry>=2.4.1,<3" poetry-plugin-export
fi

mkdir -p "$REPO_ROOT/.requirements"
REQ_FILE="$REPO_ROOT/.requirements/requirements-$PROFILE.txt"

if [ -n "$EXTRAS" ]; then
    "$POETRY" export --only main --extras "$EXTRAS" --without-hashes -o "$REQ_FILE" || {
        error "poetry export --extras '$EXTRAS' failed (profile: $PROFILE)"
    }
else
    "$POETRY" export --only main --without-hashes -o "$REQ_FILE" || {
        error "poetry export failed (profile: $PROFILE)"
    }
fi

pip install -r "$REQ_FILE" || {
    error "pip install -r '$REQ_FILE' failed"
}

# ---------------------------------------------------------------------------
# Dependency tiers.
#
# The export above is `--only main`, so for a long time nothing on this path
# installed a test runner. That is not drift -- it is what this script does --
# and it collided with pyproject's addopts, which unconditionally pass
# --reruns (pytest-rerunfailures). Result: profile-installed nodes could not
# run pytest at all; collection aborted with "unrecognized arguments". node0,
# node2 and hub2 were all in that state.
#
#   test tier -- every node. Small, and a node that cannot run its own tests
#                cannot be verified after a deploy.
#   dev  tier -- the IDE host and the designated dev nodes only. mypy, ruff,
#                pre-commit, bandit, safety, pip-audit, ipython, types-*.
#                Currently node2 and hub2 -- see docs/fleet-roles.md.
#
# Versions for the test tier come from requirements-dev.txt used as a
# constraints file, so both tiers stay pinned to the same poetry.lock export.
# ---------------------------------------------------------------------------

if [ -f "$REPO_ROOT/requirements-test.txt" ]; then
    echo "Installing test tier (every node)..."
    constraint_args=()
    [ -f "$REPO_ROOT/requirements-dev.txt" ] && constraint_args=(-c "$REPO_ROOT/requirements-dev.txt")
    pip install -r "$REPO_ROOT/requirements-test.txt" "${constraint_args[@]}" || {
        error "pip install -r requirements-test.txt failed"
    }
fi

# Whether this host is a dev node is a property of its configuration, not its
# name or its hardware profile -- node2 is a dev node AND a GPU follower running
# 18 services, so the two axes have to compose rather than being alternative
# profile names.
IS_DEV_NODE=0
[ "${AITBC_DEV_NODE:-0}" = "1" ] && IS_DEV_NODE=1
[ -f /etc/aitbc/dev-node ] && IS_DEV_NODE=1
if [ -f /etc/aitbc/blockchain.env ] && grep -qE '^AITBC_DEV_NODE=1' /etc/aitbc/blockchain.env 2>/dev/null; then
    IS_DEV_NODE=1
fi

if [ "$IS_DEV_NODE" = "1" ]; then
    if [ -f "$REPO_ROOT/requirements-dev.txt" ]; then
        echo "Dev node: installing dev tier..."
        pip install -r "$REPO_ROOT/requirements-dev.txt" || {
            error "pip install -r requirements-dev.txt failed"
        }
    else
        error "AITBC_DEV_NODE is set but requirements-dev.txt is missing"
    fi
else
    echo "Not a dev node: skipping dev tier (mypy/ruff/pre-commit/bandit/safety)."
fi
