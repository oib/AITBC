#!/bin/bash
set -euo pipefail

# ----------------------------------------------------------------------------
# Function library
#
# These are defined before the executable body so the file can be sourced for
# testing — `source setup-python-venv.sh` defines the functions and returns at
# the guard below without parsing args or touching the cache
# (tests/unit/test_setup_python_venv.py drives them on fake venv trees).
# ----------------------------------------------------------------------------

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

# Escape a literal string for use inside a sed `s|...|...|` — pattern side is
# BRE ([]^$.*\) escaped), replacement side is &,\ and the | delimiter.
_sed_pat()  { printf '%s' "$1" | sed 's/[][\.*^$/]/\\&/g'; }
_sed_repl() { printf '%s' "$1" | sed 's/[\\&|]/\\&/g'; }

# repair_copied_venv — fix up $VENV_DIR after --mode copy placed a byte-for-byte
# copy of $CACHE_VENV_DIR there. The copy still references the cache path in
# three places, all of which must be repointed:
#
#   1. bin/* script shebangs: `#!$CACHE_VENV_DIR/bin/<interp>` →
#      `#!$VENV_DIR/bin/<interp>` — only the first line, only when it names the
#      cache path; the interpreter basename (python, python3, python3.x) is
#      preserved. Without this every console script runs the *cache*
#      interpreter and `pip` installs land in the wrong tree (the hub/hub1
#      venv drift).
#   2. bin/activate* (bash, csh, fish): every literal cache path → $VENV_DIR
#      (VIRTUAL_ENV= assignments including the cygwin branch), and every
#      literal cache basename → the venv's own basename (VIRTUAL_ENV_PROMPT
#      and the PS1/prompt strings). Without this `source bin/activate` sets
#      VIRTUAL_ENV to the cache path and prepends the *cache* bin dir to PATH.
#   3. pyvenv.cfg: only the `command =` line records the create-time
#      invocation/path — rewritten to `<python-used> -m venv $VENV_DIR`.
#      home/executable/version describe the base interpreter and stay as-is.
#
# File modes are preserved: scripts are rewritten in place via a temp file +
# `cat >`, and sed -i keeps the original permissions.
repair_copied_venv() {
    local f first rest interp args base tmp cache_base dest_base

    # 1) bin/* shebangs. Symlinks (bin/python* → system interpreter) and files
    #    without a cache-path shebang are left alone.
    for f in "$VENV_DIR"/bin/*; do
        [[ -f "$f" && ! -L "$f" ]] || continue
        IFS= read -r first < "$f" 2>/dev/null || true
        [[ "$first" == '#!'*"$CACHE_VENV_DIR"* ]] || continue
        rest="${first:2}"
        rest="${rest#"${rest%%[![:space:]]*}"}"   # strip leading whitespace
        interp="${rest%%[[:space:]]*}"            # interpreter token
        args="${rest#"$interp"}"                  # anything after it (" -E")
        base="${interp##*/}"
        if [[ -z "$base" || ! -e "$VENV_DIR/bin/$base" ]]; then
            echo "⚠️ Not rewriting shebang of $f — no $VENV_DIR/bin/$base to point at" >&2
            continue
        fi
        tmp="$(mktemp)"
        if { printf '#!%s/bin/%s%s\n' "$VENV_DIR" "$base" "$args"; tail -n +2 "$f"; } > "$tmp"; then
            cat "$tmp" > "$f"
        fi
        rm -f "$tmp"
    done

    # 2) activate* — path first (so the basename pass only sees leftover prompt
    #    strings), then basename for VIRTUAL_ENV_PROMPT/PS1/setenv/set -gx.
    cache_base="$(basename -- "$CACHE_VENV_DIR")"
    dest_base="$(basename -- "$VENV_DIR")"
    for f in "$VENV_DIR"/bin/activate "$VENV_DIR"/bin/activate.csh "$VENV_DIR"/bin/activate.fish; do
        [[ -f "$f" ]] || continue
        sed -i \
            -e "s|$(_sed_pat "$CACHE_VENV_DIR")|$(_sed_repl "$VENV_DIR")|g" \
            -e "s|$(_sed_pat "$cache_base")|$(_sed_repl "$dest_base")|g" \
            "$f"
    done

    # 3) pyvenv.cfg — `command =` only.
    if [[ -f "$VENV_DIR/pyvenv.cfg" ]]; then
        sed -i "s|^command = .*|command = $(_sed_repl "$PYTHON_BIN -m venv $VENV_DIR")|" \
            "$VENV_DIR/pyvenv.cfg"
    fi
}

# assert_venv_shebangs <venv_dir>
#
# Every script in a healthy venv's bin/ shebangs to that venv's own interpreter
# ($VENV/bin/python). A venv copied out of the build cache without repair keeps
# `#!$CACHE_VENV_DIR/bin/python*` — each script then runs a foreign interpreter
# and pip installs land in the wrong tree. Scan bin/* first lines and fail on
# any shebang whose absolute interpreter path is outside the venv.
#
# Legitimate out-of-venv shebangs are allowed: generic launchers (/usr/bin/env,
# /bin/sh, /bin/bash) and the base interpreter recorded in pyvenv.cfg (the
# `executable =` path or `home =`-dir python* — e.g. /usr/bin/python3, the same
# binary the venv's bin/python* symlinks point at).
assert_venv_shebangs() {
    local venv_dir="$1"
    local bin_dir="$venv_dir/bin"
    [[ -d "$bin_dir" ]] || return 0

    # --mode symlink leaves $venv_dir a symlink at the cache venv — there the
    # cache path is the correct target, so compare against the resolved dir.
    local venv_real
    venv_real="$(cd -P "$venv_dir" 2>/dev/null && pwd -P)" || venv_real="$venv_dir"

    local home_dir="" base_exe=""
    if [[ -f "$venv_real/pyvenv.cfg" ]]; then
        home_dir="$(awk -F= '/^home[ \t]*=/{v=$2; gsub(/^[ \t]+|[ \t]+$/,"",v); print v; exit}' "$venv_real/pyvenv.cfg")"
        base_exe="$(awk -F= '/^executable[ \t]*=/{v=$2; gsub(/^[ \t]+|[ \t]+$/,"",v); print v; exit}' "$venv_real/pyvenv.cfg")"
    fi

    local offenders=()
    local f first rest interp
    for f in "$bin_dir"/*; do
        [[ -f "$f" && ! -L "$f" ]] || continue
        IFS= read -r first < "$f" 2>/dev/null || true
        [[ "$first" == '#!'* ]] || continue
        rest="${first:2}"
        rest="${rest#"${rest%%[![:space:]]*}"}"
        interp="${rest%%[[:space:]]*}"
        [[ "$interp" == /* ]] || continue   # only absolute interpreter paths
        case "$interp" in
            "$venv_dir"/*|"$venv_real"/*) continue ;;
            /bin/sh|/bin/bash|/usr/bin/sh|/usr/bin/bash|/bin/env|/usr/bin/env) continue ;;
        esac
        [[ -n "$base_exe" && "$interp" == "$base_exe" ]] && continue
        [[ -n "$home_dir" && "$interp" == "$home_dir"/python* ]] && continue
        offenders+=("$f [$first]")
    done

    if [[ ${#offenders[@]} -gt 0 ]]; then
        echo "❌ venv shebang check failed for $venv_dir — bin/* scripts point outside the venv:" >&2
        printf '   %s\n' "${offenders[@]}" >&2
        return 1
    fi
    return 0
}

# Sourcing defines the functions above and returns here — the executable body
# below only runs when the script is invoked directly.
[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0

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
        # A copied venv keeps the cache path in bin/* shebangs, activate*'s
        # VIRTUAL_ENV lines, and pyvenv.cfg's `command =`. Repoint all three
        # before activation — otherwise VIRTUAL_ENV names the cache dir and
        # PATH gets the *cache* bin prepended, so `pip`/`python` would resolve
        # to the cache interpreter and installs would land in the wrong tree.
        repair_copied_venv
        ;;
esac

# No bin/* script may shebang outside the venv — in copy mode this verifies
# the repair above; in symlink mode it is a no-op (the venv resolves to the
# cache dir, which is then the legitimate target). Runs before activation so
# a broken venv is refused before it can poison PATH.
assert_venv_shebangs "$VENV_DIR"

source "$VENV_DIR/bin/activate"

# Editable installs of repo-local packages (e.g. packages/aitbc-shared,
# packages/py/aitbc-agent-core, etc.) are recorded as the absolute path of the
# repo used to build the cache venv. When that cache is copied/symlinked into a
# new runner workspace, the original path no longer exists and the package cannot
# be imported. Reinstall from the current repo so local packages resolve.
# Use `python -m pip` rather than the `pip` entry-point script so the
# interpreter stays pinned to $VENV_DIR even if a shebang slipped through the
# repair above (a bare `pip` could still execute a foreign interpreter).
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

# The editable installs above add new bin/* entry points (aitbc, ...) — they
# shebang to the interpreter pip ran under ($VENV_DIR/bin/python). Re-assert:
# a script pointing outside the venv here means installs went to a foreign
# tree and the venv is not trustworthy.
assert_venv_shebangs "$VENV_DIR"

echo "✅ Python environment ready from cache: $CACHE_KEY"
