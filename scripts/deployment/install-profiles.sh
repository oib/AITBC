#!/bin/bash
# Install AITBC Python dependencies from poetry.lock based on a hardware/profile.
# Mirrors the profile names used by setup.sh / update.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POETRY_VENV="$REPO_ROOT/venv-poetry"
POETRY="$POETRY_VENV/bin/poetry"
PROFILE="${1:-hub}"

# shellcheck disable=SC1091
source "$REPO_ROOT/venv/bin/activate"

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
        echo "Unknown profile '$PROFILE', falling back to base dependencies"
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
    "$POETRY" export --only main --extras "$EXTRAS" --without-hashes -o "$REQ_FILE"
else
    "$POETRY" export --only main --without-hashes -o "$REQ_FILE"
fi

pip install -r "$REQ_FILE"
