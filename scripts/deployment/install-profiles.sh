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
