#!/bin/bash
# Resolve the repo python for hook/CI scripts. Prints the interpreter on stdout;
# on failure prints a single stderr line naming PYTHON and exits 1.
#
# Order — first runnable candidate wins:
#   1. $PYTHON env (validated the same way, then trusted)
#   2. <checkout>/venv/bin/python
#   3. the main checkout's venv/bin/python — `git rev-parse --git-common-dir`
#      points at the main clone's .git even inside a linked worktree, so its
#      dirname is the checkout root that holds the reference venv
#
# A candidate must be executable AND actually run Python — a dangling venv
# symlink falls through. There is deliberately no python3 fallback: a
# dependency-poor interpreter turns a hook's "ran" into "checked nothing"
# downstream (mypy/ruff absent, empty output, green-looking skip). The explicit
# opt-in for a system interpreter is `PYTHON=python3` — it stays step 1.
#
# Call sites: PYTHON="$("$(dirname "${BASH_SOURCE[0]}")/repo-python.sh")" || exit 1
set -euo pipefail

_runs() {
    [ -x "$1" ] && "$1" -c 'import sys' >/dev/null 2>&1
}

if [ -n "${PYTHON:-}" ]; then
    if _runs "$PYTHON"; then
        printf '%s\n' "$PYTHON"
        exit 0
    fi
    echo "repo-python: PYTHON='$PYTHON' is not runnable — fix it or unset it." >&2
    exit 1
fi

tried=""
_try() {
    # -n guard keeps "$top/venv/bin/python" out of the list when git failed.
    [ -n "$1" ] || return 1
    case " $tried " in
        *" $1 "*) return 1 ;;
    esac
    tried="$tried $1"
    if _runs "$1"; then
        printf '%s\n' "$1"
        return 0
    fi
    return 1
}

top="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$top" ] && _try "$top/venv/bin/python"; then
    exit 0
fi

common="$(git rev-parse --git-common-dir 2>/dev/null || true)"
if [ -n "$common" ]; then
    # Relative in a normal clone, absolute in a worktree — absolutize first.
    common_abs="$(cd "$common" 2>/dev/null && pwd -P || true)"
    if [ -n "$common_abs" ] && _try "$(dirname "$common_abs")/venv/bin/python"; then
        exit 0
    fi
fi

echo "repo-python: no runnable repo python found — set PYTHON=<interpreter> (checked:${tried:- } none)." >&2
exit 1
