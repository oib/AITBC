"""#2978 — update.sh fast-forwards the aitbc-ops companion checkout.

Before this change update.sh pulled the product repo but never refreshed
``$AITBC_OPS_ROOT`` (default ``/opt/aitbc-ops``), so fleet ops checkouts drifted
behind origin/main and the next fleet-corpus change would silently never
deploy. ``update_ops_checkout`` closes that gap — best-effort: it skips cleanly
on hosts without the checkout and warns (never aborts) on any git failure.

These pins source update.sh (never run its main()) in a scratch tree and drive
``update_ops_checkout`` against a mock ``git`` on PATH that records every
invocation to ``$CALLS_FILE``. No real git repo, network, /etc, or /var is
touched.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "deployment" / "update.sh"

# Mock git: logs every call, then answers the four subcommands
# update_ops_checkout uses. Behaviour is steered by MOCK_* env vars:
#   MOCK_OPS_GIT_DIR_RC  rev-parse --git-dir exit code (1 = no checkout)
#   MOCK_OPS_UPSTREAM    @{u} answer: unset -> origin/main, NONE -> fail,
#                        anything else printed verbatim (may be empty)
#   MOCK_GIT_FETCH_RC    fetch exit code
#   MOCK_OPS_BEHIND      rev-list --count HEAD..<upstream> output
#   MOCK_GIT_MERGE_RC    merge --ff-only exit code
_MOCK_GIT = """#!/bin/sh
printf 'git' >> "$CALLS_FILE"
printf ' %s' "$@" >> "$CALLS_FILE"
printf '\\n' >> "$CALLS_FILE"
while [ "${1:-}" = "-C" ]; do shift 2; done
cmd="${1:-}"
[ $# -gt 0 ] && shift
case "$cmd" in
    rev-parse)
        case " $* " in
            *" --git-dir "*) exit "${MOCK_OPS_GIT_DIR_RC:-0}" ;;
            *" --abbrev-ref "*)
                if [ "${MOCK_OPS_UPSTREAM:-__unset__}" = "NONE" ]; then exit 1; fi
                if [ "${MOCK_OPS_UPSTREAM:-__unset__}" = "__unset__" ]; then
                    printf 'origin/main\\n'
                else
                    printf '%s\\n' "$MOCK_OPS_UPSTREAM"
                fi
                exit 0
                ;;
            *) printf 'deadbeef\\n'; exit 0 ;;
        esac
        ;;
    fetch) exit "${MOCK_GIT_FETCH_RC:-0}" ;;
    rev-list) printf '%s\\n' "${MOCK_OPS_BEHIND:-0}"; exit 0 ;;
    merge) exit "${MOCK_GIT_MERGE_RC:-0}" ;;
    *) exit 0 ;;
esac
"""


def _write_exe(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)


def _sandbox(tmp_path: Path, **mock_env: str) -> tuple[dict[str, str], Path]:
    ops = tmp_path / "ops-checkout"
    bin_dir = tmp_path / "bin"
    calls = tmp_path / "calls"
    bin_dir.mkdir(parents=True, exist_ok=True)
    ops.mkdir(parents=True, exist_ok=True)
    _write_exe(bin_dir / "git", _MOCK_GIT)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "AITBC_OPS_ROOT": str(ops),
            "CALLS_FILE": str(calls),
        }
    )
    env.update(mock_env)
    return env, calls


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    script = f'source "{UPDATE_SH}"; update_ops_checkout\n'
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=20, check=False)


def _calls(calls: Path) -> list[str]:
    return calls.read_text().splitlines() if calls.exists() else []


def test_ops_checkout_skips_cleanly_when_absent(tmp_path: Path) -> None:
    env, calls = _sandbox(tmp_path, MOCK_OPS_GIT_DIR_RC="1")
    result = _run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipping aitbc-ops refresh" in result.stdout
    lines = _calls(calls)
    assert lines == [f"git -C {env['AITBC_OPS_ROOT']} rev-parse --git-dir"]


def test_ops_checkout_fetches_and_fast_forwards_when_behind(tmp_path: Path) -> None:
    env, calls = _sandbox(tmp_path, MOCK_OPS_BEHIND="3")
    result = _run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "fast-forwarded 3 commit(s) to origin/main" in result.stdout
    lines = _calls(calls)
    ops = env["AITBC_OPS_ROOT"]
    assert f"git -C {ops} fetch origin" in lines
    assert f"git -C {ops} rev-list --count HEAD..origin/main" in lines
    assert f"git -C {ops} merge --ff-only origin/main" in lines
    # fetch must precede the merge
    assert lines.index(f"git -C {ops} fetch origin") < lines.index(f"git -C {ops} merge --ff-only origin/main")


def test_ops_checkout_up_to_date_attempts_no_merge(tmp_path: Path) -> None:
    env, calls = _sandbox(tmp_path, MOCK_OPS_BEHIND="0")
    result = _run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "already up to date" in result.stdout
    lines = _calls(calls)
    assert not any(" merge " in line for line in lines)


def test_ops_checkout_fetch_failure_warns_and_continues(tmp_path: Path) -> None:
    env, calls = _sandbox(tmp_path, MOCK_OPS_BEHIND="2", MOCK_GIT_FETCH_RC="1")
    result = _run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "git fetch origin failed" in result.stderr
    assert not any(" merge " in line for line in _calls(calls))


def test_ops_checkout_merge_failure_warns_and_continues(tmp_path: Path) -> None:
    # Non-ff merge (dirty tree / diverged history) must not abort the update.
    env, calls = _sandbox(tmp_path, MOCK_OPS_BEHIND="2", MOCK_GIT_MERGE_RC="1")
    result = _run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "merge --ff-only origin/main failed" in result.stderr
    assert "fast-forwarded" not in result.stdout


def test_ops_checkout_falls_back_to_origin_main_without_upstream(tmp_path: Path) -> None:
    env, calls = _sandbox(tmp_path, MOCK_OPS_UPSTREAM="NONE", MOCK_OPS_BEHIND="1")
    result = _run(env)

    assert result.returncode == 0, result.stdout + result.stderr
    lines = _calls(calls)
    ops = env["AITBC_OPS_ROOT"]
    assert f"git -C {ops} fetch origin" in lines
    assert f"git -C {ops} merge --ff-only origin/main" in lines
    assert "fast-forwarded 1 commit(s) to origin/main" in result.stdout
