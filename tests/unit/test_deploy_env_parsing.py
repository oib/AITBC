"""DEPLOY-ENV-SOURCED-AS-SHELL-1 — env files are parsed, never executed.

update.sh and run-migrations.sh used to `source` systemd EnvironmentFiles.
That is a different language: a value with an unquoted space or an inline
`# comment` errored (swallowed by 2>/dev/null), a line like
``X=$(rm -rf x)`` *ran*, and a file bash could not parse degraded silently to
a default DATABASE_URL — meaning the migration ran against the wrong
database instead of failing.

The fix reads values through scripts/utils/systemd-env.sh, an EnvironmentFile
parser in a subprocess. These tests cover the parser's accepted/malformed
forms, that sourcing hazards are inert, and that run-migrations.sh fails a
service whose DATABASE_URL cannot be read instead of skipping to a default.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "utils" / "systemd-env.sh"
RUN_MIGRATIONS = REPO_ROOT / "scripts" / "deployment" / "run-migrations.sh"
UPDATE_SH = REPO_ROOT / "scripts" / "deployment" / "update.sh"


def _get(env_file: Path, key: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(HELPER), "get", str(env_file), key], capture_output=True, text=True)


# ---------------------------------------------------------------------------
# systemd-env.sh parse rules
# ---------------------------------------------------------------------------


def test_get_handles_the_forms_systemd_accepts(tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "DATABASE_URL=sqlite:////var/lib/aitbc/data/x.db # the live db",
                'QUOTED="double quoted"',
                "SINGLE='single quoted'",
                "export EXPORTED=yes",
                "  SPACED = padded ",
                "not an assignment",
            ]
        )
    )

    # systemd keeps an inline ' # comment' inside an unquoted value — the
    # helper must deliver the same text a service would get.
    assert _get(env_file, "DATABASE_URL").stdout.strip() == "sqlite:////var/lib/aitbc/data/x.db # the live db"
    assert _get(env_file, "QUOTED").stdout.strip() == "double quoted"
    assert _get(env_file, "SINGLE").stdout.strip() == "single quoted"
    assert _get(env_file, "EXPORTED").stdout.strip() == "yes"
    assert _get(env_file, "SPACED").stdout.strip() == "padded"


def test_get_never_executes_the_file(tmp_path):
    """A sourcing parser would create the sentinel; an EnvironmentFile read must not."""
    sentinel = tmp_path / "executed"
    env_file = tmp_path / "svc.env"
    env_file.write_text(f"PAYLOAD=$(touch {sentinel})\nDATABASE_URL=ok\n")

    result = _get(env_file, "DATABASE_URL")

    assert result.stdout.strip() == "ok"
    assert not sentinel.exists()


def test_get_reports_malformed_lines_with_rc2(tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text('DATABASE_URL="sqlite:///unclosed\n')

    result = _get(env_file, "DATABASE_URL")

    assert result.returncode == 2


def test_a_hash_without_preceding_space_stays_in_the_value(tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text("TOKEN=abc#123\n")

    assert _get(env_file, "TOKEN").stdout.strip() == "abc#123"


# ---------------------------------------------------------------------------
# update.sh — get_node_role reads the file instead of executing it
# ---------------------------------------------------------------------------


def test_get_node_role_parses_values_sourcing_would_break(tmp_path):
    sentinel = tmp_path / "executed"
    blockchain_env = tmp_path / "blockchain.env"
    node_env = tmp_path / "node.env"
    blockchain_env.write_text(
        "\n".join(
            [
                "BLOCKCHAIN_MODE=follower",
                "# keep it a follower",
                "MARKET_ROLE=shop",
                f"PAYLOAD=$(touch {sentinel})",
            ]
        )
    )
    node_env.write_text("")

    script = f"""
        source {UPDATE_SH}
        AITBC_NODE_ENV_FILE={node_env}
        AITBC_BLOCKCHAIN_ENV_FILE={blockchain_env}
        BLOCKCHAIN_ENV_FILE={blockchain_env}
        NODE_ENV_FILE={node_env}
        detect_gpu() {{ DETECTED_HARDWARE=nogpu; GPU_NAME=""; GPU_COUNT=0; }}
        get_node_role
    """
    env = {**os.environ, "AITBC_ROOT": str(REPO_ROOT)}
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("follower:shop:nogpu")
    assert not sentinel.exists()


# ---------------------------------------------------------------------------
# run-migrations.sh — an unreadable DATABASE_URL fails the service
# ---------------------------------------------------------------------------

_ALEMBIC_STUB = """#!/bin/bash
# Stub alembic: `upgrade head` echoes the DATABASE_URL it was handed.
echo "STUB_ALEMBIC DATABASE_URL=${DATABASE_URL:-<unset>}"
exit 0
"""


def _migration_scratch(tmp_path: Path, svc: str, env_contents: str | None) -> dict:
    """A fake apps tree, /etc/aitbc and systemd dir for one service."""
    apps = tmp_path / "apps" / svc
    apps.mkdir(parents=True)
    (apps / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")

    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    alembic = venv_bin / "alembic"
    alembic.write_text(_ALEMBIC_STUB)
    alembic.chmod(alembic.stat().st_mode | stat.S_IXUSR)

    # The script resolves helpers under AITBC_ROOT — give the scratch tree the
    # real env parser and a no-op agent_followup so the follow-up hook stays quiet.
    utils = tmp_path / "scripts" / "utils"
    utils.mkdir(parents=True)
    (utils / "systemd-env.sh").write_text(HELPER.read_text())
    (utils / "systemd-env.sh").chmod(0o755)
    (utils / "agent_followup.sh").write_text(
        "agent_followup_init() { :; }\n"
        "agent_record_warning() { :; }\n"
        "agent_record_error() { :; }\n"
        "agent_print_followup() { :; }\n"
    )

    etc = tmp_path / "etc-aitbc"
    etc.mkdir()
    if env_contents is not None:
        (etc / f"aitbc-{svc}.env").write_text(env_contents)

    systemd = tmp_path / "systemd"
    systemd.mkdir()
    (systemd / f"aitbc-{svc}.service").write_text("[Unit]\n")

    return {"root": tmp_path, "etc": etc, "systemd": systemd}


def _run_migrations(scratch: dict) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "AITBC_ROOT": str(scratch["root"]),
        "VENV_DIR": str(scratch["root"] / "venv"),
        "AITBC_ETC_DIR": str(scratch["etc"]),
        "AITBC_SYSTEMD_DIR": str(scratch["systemd"]),
    }
    return subprocess.run(["bash", str(RUN_MIGRATIONS)], capture_output=True, text=True, env=env, timeout=60)


def test_malformed_database_url_fails_the_service(tmp_path):
    scratch = _migration_scratch(tmp_path, "zzmig-test", 'DATABASE_URL="sqlite:///unclosed\n')

    result = _run_migrations(scratch)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "malformed DATABASE_URL" in result.stderr
    assert "STUB_ALEMBIC" not in result.stdout


def test_env_value_with_inline_comment_reaches_alembic_verbatim(tmp_path):
    """systemd keeps ' # comment' inside an unquoted value, so the helper must
    deliver it verbatim — the only safe fix is comments on their own lines."""
    scratch = _migration_scratch(
        tmp_path,
        "zzmig-test",
        "DATABASE_URL=sqlite:////var/tmp/ok.db # the live trading db\n",
    )

    result = _run_migrations(scratch)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "STUB_ALEMBIC DATABASE_URL=sqlite:////var/tmp/ok.db # the live trading db" in result.stdout


def test_absent_database_url_keeps_the_existing_skip_semantics(tmp_path):
    """blockchain-node without DATABASE_URL is still skipped, not failed."""
    scratch = _migration_scratch(tmp_path, "blockchain-node", "")

    result = _run_migrations(scratch)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipping blockchain-node" in result.stdout
