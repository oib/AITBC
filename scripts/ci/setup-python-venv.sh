#!/bin/bash
set -euo pipefail

REPO_DIR="$(pwd)"
VENV_DIR=""
REQUIREMENTS_FILE=""
SKIP_REQUIREMENTS="false"
MODE="symlink"
EXTRA_PACKAGES=""
CACHE_ROOT="/var/cache/aitbc/python-venvs"
PIP_CACHE_ROOT="${PIP_CACHE_ROOT:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Writable fallback roots for unprivileged CI runners.
FALLBACK_CACHE_ROOT=""
FALLBACK_PIP_CACHE_ROOT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-dir)
            REPO_DIR="$2"
            shift 2
            ;;
        --venv-dir)
            VENV_DIR="$2"
            shift 2
            ;;
        --requirements-file)
            REQUIREMENTS_FILE="$2"
            shift 2
            ;;
        --skip-requirements)
            SKIP_REQUIREMENTS="true"
            shift
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --extra-packages)
            EXTRA_PACKAGES="$2"
            shift 2
            ;;
        --cache-root)
            CACHE_ROOT="$2"
            shift 2
            ;;
        --pip-cache-root)
            PIP_CACHE_ROOT="$2"
            shift 2
            ;;
        --python-bin)
            PYTHON_BIN="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

VENV_DIR="${VENV_DIR:-$REPO_DIR/venv}"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-$REPO_DIR/requirements.txt}"

# Fall back to repo-local writable cache directories when the configured
# system-wide cache roots are not usable (e.g. unprivileged CI runners).
FALLBACK_CACHE_ROOT="$REPO_DIR/.cache/python-venvs"
FALLBACK_PIP_CACHE_ROOT="$REPO_DIR/.cache/pip"

if [[ -z "$PIP_CACHE_ROOT" ]]; then
    PIP_CACHE_ROOT="${CACHE_ROOT}/pip"
fi

if [[ ! -d "$CACHE_ROOT" ]] && ! mkdir -p "$CACHE_ROOT" 2>/dev/null; then
    echo "⚠️ Cache root $CACHE_ROOT is not writable, falling back to $FALLBACK_CACHE_ROOT" >&2
    CACHE_ROOT="$FALLBACK_CACHE_ROOT"
    mkdir -p "$CACHE_ROOT"
fi

if [[ ! -d "$PIP_CACHE_ROOT" ]] && ! mkdir -p "$PIP_CACHE_ROOT" 2>/dev/null; then
    echo "⚠️ Pip cache root $PIP_CACHE_ROOT is not writable, falling back to $FALLBACK_PIP_CACHE_ROOT" >&2
    PIP_CACHE_ROOT="$FALLBACK_PIP_CACHE_ROOT"
    mkdir -p "$PIP_CACHE_ROOT"
fi

if [[ "$SKIP_REQUIREMENTS" == "true" ]]; then
    REQUIREMENTS_FILE=""
fi

if [[ "$MODE" != "symlink" && "$MODE" != "copy" ]]; then
    echo "Invalid mode: $MODE" >&2
    exit 1
fi

if [[ ! -d "$REPO_DIR" ]]; then
    echo "Repository directory not found: $REPO_DIR" >&2
    exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Python binary not found: $PYTHON_BIN" >&2
    exit 1
fi

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1
export PIP_PROGRESS_BAR=off
export PIP_CACHE_DIR="$PIP_CACHE_ROOT"

mkdir -p "$CACHE_ROOT" "$PIP_CACHE_ROOT"

PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
if [[ -n "$REQUIREMENTS_FILE" && -f "$REQUIREMENTS_FILE" ]]; then
    REQUIREMENTS_HASH="$(sha256sum "$REQUIREMENTS_FILE" | awk '{print $1}' | cut -c1-16)"
else
    REQUIREMENTS_HASH="no-req"
fi
EXTRA_HASH="$(printf '%s' "$EXTRA_PACKAGES" | sha256sum | awk '{print $1}' | cut -c1-16)"
CACHE_KEY="py${PYTHON_VERSION}-req${REQUIREMENTS_HASH}-extra${EXTRA_HASH}"
CACHE_VENV_DIR="$CACHE_ROOT/$CACHE_KEY"
LOCK_FILE="$CACHE_ROOT/$CACHE_KEY.lock"

cached_environment_is_valid() {
    [[ -x "$CACHE_VENV_DIR/bin/python" ]] || return 1
    [[ -x "$CACHE_VENV_DIR/bin/pip" ]] || return 1

    "$CACHE_VENV_DIR/bin/python" -c 'import sys; print(sys.executable)' >/dev/null 2>&1 || return 1
    "$CACHE_VENV_DIR/bin/pip" --version >/dev/null 2>&1 || return 1
}

build_cached_environment() {
    rm -rf "$CACHE_VENV_DIR"
    "$PYTHON_BIN" -m venv "$CACHE_VENV_DIR"

    if ! "$CACHE_VENV_DIR/bin/python" -m pip install -q --upgrade pip setuptools wheel --no-cache-dir; then
        rm -rf "$CACHE_VENV_DIR"
        return 1
    fi

    if [[ -n "$REQUIREMENTS_FILE" && -f "$REQUIREMENTS_FILE" ]]; then
        # `-e file://...` lines point at the absolute path of the repo checkout
        # that had poetry.lock exported on it (packages/aitbc-shared, etc.) --
        # meaningless on any other checkout, including this runner's own
        # per-job workspace. Skip them here; the loop below reinstalls the
        # same local packages editable from $REPO_DIR once the venv is in
        # place, which is the only path that is ever valid in CI.
        FILTERED_REQUIREMENTS="$(mktemp)"
        grep -v '^-e file://' "$REQUIREMENTS_FILE" > "$FILTERED_REQUIREMENTS"
        if ! "$CACHE_VENV_DIR/bin/python" -m pip install -q -r "$FILTERED_REQUIREMENTS" --no-cache-dir; then
            rm -f "$FILTERED_REQUIREMENTS"
            rm -rf "$CACHE_VENV_DIR"
            return 1
        fi
        rm -f "$FILTERED_REQUIREMENTS"
    fi

    if [[ -n "$EXTRA_PACKAGES" ]]; then
        read -r -a extra_array <<< "$EXTRA_PACKAGES"
        if ! "$CACHE_VENV_DIR/bin/python" -m pip install -q "${extra_array[@]}" --no-cache-dir; then
            rm -rf "$CACHE_VENV_DIR"
            return 1
        fi
    fi
}

if command -v flock >/dev/null 2>&1; then
    exec 9>"$LOCK_FILE"
    flock 9
fi

if cached_environment_is_valid; then
    echo "✅ Reusing cached Python environment: $CACHE_KEY"
else
    if [[ -e "$CACHE_VENV_DIR" ]]; then
        echo "⚠️ Invalid cached Python environment detected, rebuilding: $CACHE_KEY"
        rm -rf "$CACHE_VENV_DIR"
    else
        echo "📦 Building cached Python environment: $CACHE_KEY"
    fi
    build_cached_environment
fi

rm -rf "$VENV_DIR"

case "$MODE" in
    symlink)
        ln -s "$CACHE_VENV_DIR" "$VENV_DIR"
        ;;
    copy)
        mkdir -p "$VENV_DIR"
        if command -v rsync >/dev/null 2>&1; then
            rsync -a --delete "$CACHE_VENV_DIR/" "$VENV_DIR/"
        else
            cp -a "$CACHE_VENV_DIR/." "$VENV_DIR/"
        fi
        ;;
esac

source "$VENV_DIR/bin/activate"

# Editable installs of repo-local packages (e.g. packages/aitbc-shared,
# packages/py/aitbc-agent-core, etc.) are recorded as the absolute path of the
# repo used to build the cache venv. When that cache is copied/symlinked into a
# new runner workspace, the original path no longer exists and the package cannot
# be imported. Reinstall from the current repo so local packages resolve.
# Use `python -m pip` instead of the `pip` script because the copied venv's
# `bin/pip` script still has a shebang pointing at the original cache python.
failed=()
for pkg_dir in "$REPO_DIR/packages/aitbc-shared" "$REPO_DIR"/packages/py/*; do
    if [ -d "$pkg_dir" ] && [ -f "$pkg_dir/pyproject.toml" ]; then
        if ! "$VENV_DIR/bin/python" -m pip install -q --force-reinstall --no-deps -e "$pkg_dir" >/dev/null 2>&1; then
            failed+=("$pkg_dir")
        fi
    fi
done
if [ ${#failed[@]} -gt 0 ]; then
    echo "❌ Failed to install repo-local packages: ${failed[*]}" >&2
    exit 1
fi

echo "✅ Python environment ready from cache: $CACHE_KEY"
