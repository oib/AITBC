"""V23-79 — the deploy path runs migrations, and the readiness check can fail.

Two halves of one finding:

* ``scripts/deployment/run-migrations.sh`` is the single implementation of "migrate every
  service safely". ``update.sh`` and ``deploy.sh`` both call it; before this it lived only
  inside ``update.sh``, so a first install never migrated at all.
* ``check_migrations`` in ``scripts/check-production-readiness.py`` is what notices when
  that has not happened. It could not: a database with no ``alembic_version`` table was
  reported as "skipped" and passed, and blockchain-node was excluded from the check
  entirely by an un-interpolated ``%(here)s``.

The ``check_migrations`` tests run against a temporary apps tree and a stub ``alembic``.
That is not only for speed — this check's whole job is to connect to production databases
with production credentials, and a test suite must not.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
READINESS = REPO_ROOT / "scripts" / "check-production-readiness.py"
RUN_MIGRATIONS = REPO_ROOT / "scripts" / "deployment" / "run-migrations.sh"
UPDATE_SH = REPO_ROOT / "scripts" / "deployment" / "update.sh"
DEPLOY_SH = REPO_ROOT / "scripts" / "deployment" / "deploy.sh"


@pytest.fixture(scope="module")
def cpr():
    """The readiness script, loaded by path — its filename is not a Python identifier."""
    spec = importlib.util.spec_from_file_location("check_production_readiness", READINESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# script_location resolution — the bug that hid blockchain-node
# ---------------------------------------------------------------------------


def test_script_location_interpolates_here(cpr, tmp_path):
    """``%(here)s`` is Alembic's own token for the ini file's directory."""
    ini = tmp_path / "alembic.ini"
    ini.write_text("[alembic]\nscript_location = %(here)s/migrations\n")

    assert cpr._script_location(ini) == tmp_path / "migrations"


def test_script_location_resolves_a_relative_path_against_the_ini(cpr, tmp_path):
    ini = tmp_path / "alembic.ini"
    ini.write_text("[alembic]\nscript_location = alembic\n")

    assert cpr._script_location(ini) == tmp_path / "alembic"


def test_every_alembic_app_in_the_tree_is_discovered(cpr):
    """The check must see all seven, blockchain-node included.

    blockchain-node is the one that regressed: it is the only app whose alembic.ini uses
    ``%(here)s``, so it was the only one ``_has_migrations`` answered False for — and it is
    the app whose deployed database was found with no ``alembic_version`` table (V23-49).
    """
    apps = REPO_ROOT / "apps"
    found = {p.parent.name for p in apps.glob("*/alembic.ini") if cpr._has_migrations(p.parent)}
    configured = {p.parent.name for p in apps.glob("*/alembic.ini")}

    assert found == configured, f"configured but not discovered: {sorted(configured - found)}"
    assert "blockchain-node" in found


# ---------------------------------------------------------------------------
# Service environment — which database the check actually talks to
# ---------------------------------------------------------------------------


def test_env_file_parsing_handles_the_forms_systemd_accepts(cpr, tmp_path):
    env_file = tmp_path / "svc.env"
    env_file.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "DATABASE_URL=sqlite:////var/lib/aitbc/data/x.db",
                'QUOTED="double quoted"',
                "SINGLE='single quoted'",
                "export EXPORTED=yes",
                "  SPACED = padded ",
                "not an assignment",
            ]
        )
    )

    parsed = cpr._read_env_file(env_file)

    assert parsed["DATABASE_URL"] == "sqlite:////var/lib/aitbc/data/x.db"
    assert parsed["QUOTED"] == "double quoted"
    assert parsed["SINGLE"] == "single quoted"
    assert parsed["EXPORTED"] == "yes"
    assert parsed["SPACED"] == "padded"
    assert "not an assignment" not in parsed


def test_service_env_prefers_the_prefixed_filename(cpr, tmp_path, monkeypatch):
    """``aitbc-<svc>.env`` wins over ``<svc>.env``, matching run-migrations.sh.

    pool-hub is the reason this order is fixed rather than incidental: it is the one service
    with a file under both names.
    """
    monkeypatch.setattr(cpr, "ETC_AITBC", tmp_path)
    (tmp_path / "aitbc-pool-hub.env").write_text("DATABASE_URL=prefixed\n")
    (tmp_path / "pool-hub.env").write_text("DATABASE_URL=bare\n")

    env, source = cpr._service_env("pool-hub")

    assert env["DATABASE_URL"] == "prefixed"
    assert source == tmp_path / "aitbc-pool-hub.env"


def test_service_env_is_empty_when_the_service_has_no_file(cpr, tmp_path, monkeypatch):
    """Not a failure: trading has no env file and its env.py default is the right database."""
    monkeypatch.setattr(cpr, "ETC_AITBC", tmp_path)

    assert cpr._service_env("trading") == ({}, None)


# ---------------------------------------------------------------------------
# check_migrations verdicts, against a stub alembic
# ---------------------------------------------------------------------------

_STUB = """#!/usr/bin/env python3
import json, os, pathlib, sys

scenario = json.loads(pathlib.Path(os.environ["STUB_SCENARIOS"]).read_text())[pathlib.Path.cwd().name]

if sys.argv[1] == "heads":
    sys.stdout.write(scenario.get("head", ""))
    sys.exit(0)

if scenario.get("exit", 0):
    sys.stderr.write(scenario.get("stderr", "could not connect\\n"))
    sys.exit(scenario["exit"])

if scenario.get("echo_db_url"):
    sys.stdout.write(os.environ.get("DATABASE_URL", "<unset>") + "\\n")
else:
    sys.stdout.write(scenario.get("current", ""))
sys.exit(0)
"""


@pytest.fixture
def fake_deployment(cpr, tmp_path, monkeypatch):
    """An apps tree, an /etc/aitbc, and a stub alembic that answers from a scenario file."""
    apps = tmp_path / "apps"
    etc = tmp_path / "etc"
    etc.mkdir()

    stub = tmp_path / "alembic"
    stub.write_text(_STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    scenarios_path = tmp_path / "scenarios.json"

    monkeypatch.setattr(cpr, "APPS_DIR", apps)
    monkeypatch.setattr(cpr, "ETC_AITBC", etc)
    monkeypatch.setattr(cpr, "ALEMBIC_BIN", stub)
    monkeypatch.setenv("STUB_SCENARIOS", str(scenarios_path))

    def build(scenarios: dict[str, dict]) -> None:
        for name in scenarios:
            versions = apps / name / "alembic" / "versions"
            versions.mkdir(parents=True)
            (versions / "0001_initial.py").write_text("revision = '0001'\n")
            (apps / name / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")
        scenarios_path.write_text(json.dumps(scenarios))

    build.etc = etc  # type: ignore[attr-defined]
    return build


def test_a_database_at_head_passes(cpr, fake_deployment, capsys):
    fake_deployment({"trading": {"head": "003 (head)\n", "current": "003 (head)\n"}})

    assert cpr.check_migrations() is True
    assert "✅ Migrations [trading]" in capsys.readouterr().out


def test_a_database_behind_head_fails_and_names_the_head(cpr, fake_deployment, capsys):
    fake_deployment({"trading": {"head": "003 (head)\n", "current": "001\n"}})

    assert cpr.check_migrations() is False
    out = capsys.readouterr().out
    assert "behind head — 001" in out
    assert "head: 003 (head)" in out


def test_a_never_migrated_database_fails(cpr, fake_deployment, capsys):
    """The regression this fixes.

    ``alembic current`` against a database with no ``alembic_version`` table exits 0 and
    writes nothing to stdout — the INFO banner goes to stderr. That was read as "no revision
    applied (skipped)" and left the result untouched, so a database that had never been
    migrated passed a check that a database one revision behind failed. gpu, edge and
    pool-hub were all in that state on the hub while this check reported no problem.
    """
    fake_deployment({"gpu": {"head": "b8f3a2c91d04 (head)\n", "current": ""}})

    assert cpr.check_migrations() is False
    assert "never migrated — no alembic_version table" in capsys.readouterr().out


def test_an_unreachable_database_fails(cpr, fake_deployment, capsys):
    fake_deployment({"pool-hub": {"exit": 1, "stderr": "could not connect to server\n"}})

    assert cpr.check_migrations() is False
    assert "FAILED" in capsys.readouterr().out


def test_one_bad_app_fails_the_whole_check(cpr, fake_deployment, capsys):
    """A per-app loop that reports and continues still has to return False overall."""
    fake_deployment(
        {
            "trading": {"head": "003 (head)\n", "current": "003 (head)\n"},
            "gpu": {"head": "b8f (head)\n", "current": ""},
        }
    )

    assert cpr.check_migrations() is False
    out = capsys.readouterr().out
    assert "✅ Migrations [trading]" in out
    assert "❌ Migrations [gpu]" in out


def test_the_service_env_file_reaches_alembic(cpr, fake_deployment, capsys):
    """The point of reading /etc/aitbc: otherwise env.py falls back to its own default.

    coordinator-api's default is a local SQLite file while the service runs on Postgres, so
    without this the check answered — with a tick — for a database nothing uses.
    """
    fake_deployment({"coordinator-api": {"head": "a3e (head)\n", "echo_db_url": True}})
    (fake_deployment.etc / "aitbc-coordinator-api.env").write_text(  # type: ignore[attr-defined]
        "DATABASE_URL=postgresql://from-the-env-file/coordinator\n"
    )

    cpr.check_migrations()

    assert "postgresql://from-the-env-file/coordinator" in capsys.readouterr().out


def test_an_ambient_database_url_does_not_leak_into_a_service(cpr, fake_deployment, capsys, monkeypatch):
    """One service's URL reaching another's `upgrade head` is the worst failure here.

    run-migrations.sh unsets it between services for the same reason; this check has to
    match, or it validates a database the deploy will not migrate.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://ambient/wrong")
    fake_deployment({"trading": {"head": "003 (head)\n", "echo_db_url": True}})

    cpr.check_migrations()

    out = capsys.readouterr().out
    assert "ambient" not in out
    assert "<unset>" in out


# ---------------------------------------------------------------------------
# run-migrations.sh — one implementation, called by both deploy paths
# ---------------------------------------------------------------------------


def test_run_migrations_script_exists_and_is_executable():
    assert RUN_MIGRATIONS.is_file()
    assert os.access(RUN_MIGRATIONS, os.X_OK), "deploy.sh and update.sh exec it, not source it"


def test_run_migrations_passes_shellcheck():
    shellcheck = subprocess.run(["which", "shellcheck"], capture_output=True, text=True)
    if shellcheck.returncode != 0:
        pytest.skip("shellcheck not installed")
    result = subprocess.run(["shellcheck", "--severity=warning", str(RUN_MIGRATIONS)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("caller", [UPDATE_SH, DEPLOY_SH])
def test_both_deploy_paths_call_the_shared_script(caller):
    """deploy.sh is the half that was missing: a first install started services unmigrated."""
    assert "run-migrations.sh" in caller.read_text(), f"{caller.name} does not run migrations"


def test_update_sh_no_longer_carries_its_own_copy():
    """The logic moved rather than being duplicated — two copies would drift apart.

    ``print_summary`` still *prints* ``alembic upgrade head`` as a manual follow-up hint, so
    this looks for an executed invocation rather than the string.
    """
    printing = ("echo", "log", "warning", "error", "success", "#")
    executed = [
        line.strip()
        for line in UPDATE_SH.read_text().splitlines()
        if "alembic" in line and "upgrade" in line and not line.strip().startswith(printing)
    ]

    assert not executed, f"update.sh still runs alembic itself: {executed}"


def test_no_unit_gained_an_execstartpre_migration():
    """Deliberately not the fix — recorded so a later sweep does not add one by reflex.

    Four blockchain-node units (node, p2p, rpc, sync) share one SQLite chain database, so an
    ExecStartPre on each is four concurrent `upgrade head` on one file. blockchain-node's
    Alembic default also targets a database no node uses (V23-49), and SQLite migrations here
    go through batch_alter_table(recreate="always"), which a unit cannot do safely to its own
    running siblings. Migrations are a deploy step, with the services stopped.
    """
    offenders = [
        unit.relative_to(REPO_ROOT) for unit in (REPO_ROOT / "apps").rglob("*.service") if "alembic" in unit.read_text()
    ]
    assert not offenders, f"units invoking alembic: {offenders}"
