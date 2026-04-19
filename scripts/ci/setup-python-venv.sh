#!/bin/bash
set -euo pipefail

REPO_DIR="$(pwd)"
VENV_DIR=""
REQUIREMENTS_FILE=""
SKIP_REQUIREMENTS="false"
MODE="symlink"
EXTRA_PACKAGES=""
CACHE_ROOT="/var/cache/aitbc/python-venvs"
PIP_CACHE_ROOT="/var/cache/aitbc/pip"
PYTHON_BIN="${PYTHON_BIN:-python3}"

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

build_cached_environment() {
    local temp_dir
    temp_dir="${CACHE_VENV_DIR}.tmp.$$"

    rm -rf "$temp_dir"
    "$PYTHON_BIN" -m venv "$temp_dir"
    source "$temp_dir/bin/activate"

    python -m pip install -q --upgrade pip setuptools wheel

    if [[ -n "$REQUIREMENTS_FILE" && -f "$REQUIREMENTS_FILE" ]]; then
        python -m pip install -q -r "$REQUIREMENTS_FILE"
    fi

    if [[ -n "$EXTRA_PACKAGES" ]]; then
        read -r -a extra_array <<< "$EXTRA_PACKAGES"
        python -m pip install -q "${extra_array[@]}"
    fi

    deactivate || true
    mv "$temp_dir" "$CACHE_VENV_DIR"
}

if command -v flock >/dev/null 2>&1; then
    exec 9>"$LOCK_FILE"
    flock 9
fi

if [[ -x "$CACHE_VENV_DIR/bin/python" ]]; then
    echo "✅ Reusing cached Python environment: $CACHE_KEY"
else
    echo "📦 Building cached Python environment: $CACHE_KEY"
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
echo "✅ Python environment ready from cache: $CACHE_KEY"
