"""Tests for ``aitbc system file-info`` and ``aitbc system env-names`` (CLI-2).

file-info is the safe metadata view for sensitive files: it never dumps
content, and ``--field`` hard-refuses denied names (private_key, *_key,
secrets) — a denied value must never reach stdout or the log. env-names
lists variable NAMES only across a unit's EnvironmentFiles (drop-ins
included), never values.

All files are created under tmp_path; _ALLOWED_READ_PREFIXES is patched to
point there so no real /var/lib/aitbc or /etc/aitbc content is touched.
"""

import json
import os
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.system as system_mod
from aitbc_cli.commands.system import system


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def allowed(tmp_path):
    """Patch the read allowlist to tmp_path for the duration of a test."""
    with mock.patch.object(system_mod, "_ALLOWED_READ_PREFIXES", (str(tmp_path) + "/",)):
        yield tmp_path


def _write_json(path, obj):
    path.write_text(json.dumps(obj))
    return path


# ---------------------------------------------------------------- file-info


def test_file_info_reports_metadata_and_json_keys(runner, allowed):
    f = _write_json(allowed / "node.json", {"address": "0xabc", "private_key": "0xdeadbeef", "label": "n1"})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f)])
    assert result.exit_code == 0, result.output
    assert "size" in result.output
    assert "mtime" in result.output
    assert "mode" in result.output
    assert "owner" in result.output
    # top-level key names are listed, but not a hash of the file
    for key in ("address", "label", "private_key"):
        assert key in result.output
    assert "sha256" not in result.output
    assert "0xdeadbeef" not in result.output


def test_file_info_field_prints_scalar(runner, allowed):
    f = _write_json(allowed / "node.json", {"Address": "0xAbC123", "label": "n1"})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "address"])
    assert result.exit_code == 0, result.output
    assert "0xAbC123" in result.output


@pytest.mark.parametrize(
    "denied",
    [
        # original denylist
        "private_key",
        "PRIVATE_KEY",
        "password",
        "api_key",
        "node_key",
        "seed",
        # separator-insensitive exact names (CLI-2 hardening)
        "privatekey",
        "private-key",
        "apikey",
        "api-key",
        "secretkey",
        "passphrase",
        "pass_phrase",
        "passwd",
        "credential",
        "credentials",
        # "<prefix>key" names — private/secret/api/auth/signing/access
        "authkey",
        "auth-key",
        "signingkey",
        "signing_key",
        "accesskey",
        "access-key",
    ],
)
def test_file_info_field_denied_names_refused(runner, allowed, capsys, caplog, denied):
    secret = "0xSECRETNEVERPRINTED123"
    f = _write_json(allowed / "node.json", {denied: secret, "address": "0xabc"})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", denied])
    assert result.exit_code != 0
    assert "refused" in result.output.lower() or "denied" in result.output.lower()
    # the denied value must never reach stdout or the log
    assert secret not in capsys.readouterr().out
    assert secret not in caplog.text


@pytest.mark.parametrize("allowed_name", ["address", "pubkey", "monkey", "keynote"])
def test_file_info_field_allowed_names_unchanged(runner, allowed, allowed_name):
    """Names merely *ending* in "key" stay allowed — only the listed prefixes deny."""
    f = _write_json(allowed / "node.json", {allowed_name: "0xAbC123"})
    result = runner.invoke(
        system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", allowed_name]
    )
    assert result.exit_code == 0, result.output
    assert "0xAbC123" in result.output


def test_file_info_field_denied_inside_nested_value(runner, allowed, capsys):
    secret = "0xSECRETNEVERPRINTED123"
    f = _write_json(allowed / "node.json", {"credentials": {"inner": {"private_key": secret}}})
    result = runner.invoke(
        system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "credentials"]
    )
    assert result.exit_code != 0
    assert secret not in capsys.readouterr().out


def test_file_info_field_non_scalar_refused(runner, allowed):
    f = _write_json(allowed / "node.json", {"peers": ["a", "b"]})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "peers"])
    assert result.exit_code != 0
    assert "scalar" in result.output


def test_file_info_field_over_200_chars_refused(runner, allowed, capsys):
    big = "x" * 201
    f = _write_json(allowed / "node.json", {"note": big})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "note"])
    assert result.exit_code != 0
    assert big not in capsys.readouterr().out


def test_file_info_field_missing_name(runner, allowed):
    f = _write_json(allowed / "node.json", {"address": "0xabc"})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "nosuch"])
    assert result.exit_code != 0
    assert "no such top-level field" in result.output


def test_file_info_field_on_non_json_refused(runner, allowed):
    f = allowed / "plain.log"
    f.write_text("just a log line\n")
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "address"])
    assert result.exit_code != 0
    assert "JSON" in result.output


def test_file_info_rejects_path_outside_allowlist(runner, allowed):
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", "/etc/passwd"])
    assert result.exit_code != 0
    assert "not allowed" in result.output


def test_file_info_rejects_symlink_escaping_allowlist(runner, allowed, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir(exist_ok=True)
    secret_file = _write_json(outside / "w.json", {"address": "0xabc"})
    link = allowed / "link.json"
    os.symlink(secret_file, link)
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(link)])
    assert result.exit_code != 0
    assert "not allowed" in result.output


def test_system_file_unchanged_still_dumps_content(runner, allowed):
    """Regression: the existing `system file` behaviour is untouched."""
    f = allowed / "node.json"
    f.write_text('{"address": "0xabc", "private_key": "0xdeadbeef"}')
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file", "--path", str(f)])
    assert result.exit_code == 0
    assert "0xdeadbeef" in result.output


# ---------------------------------------------------------------- env-names


def _systemctl_result(stdout: str, returncode: int = 0):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr="")


def test_env_names_lists_all_declared_files(runner, tmp_path):
    main_env = tmp_path / "svc.env"
    drop_env = tmp_path / "svc-dropin.env"
    main_env.write_text("FOO=1\nBAR=2\n# comment\n")
    drop_env.write_text("BAZ=3\n")
    show = f"{main_env} (ignore_errors=no) {drop_env} (ignore_errors=yes)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result(show)):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc"])
    assert result.exit_code == 0, result.output
    for name in ("FOO", "BAR", "BAZ"):
        assert name in result.output
    # values never print
    assert "=1" not in result.output and "=2" not in result.output and "=3" not in result.output
    assert "optional" in result.output  # the '-' / ignore_errors=yes file is marked


def test_env_names_missing_file_noted(runner, tmp_path):
    gone = tmp_path / "gone.env"
    show = f"{gone} (ignore_errors=yes)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result(show)):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc"])
    assert result.exit_code == 0, result.output
    assert "missing" in result.output


def test_env_names_filter_reports_set_unset(runner, tmp_path):
    env = tmp_path / "svc.env"
    env.write_text("FOO=1\n")
    show = f"{env} (ignore_errors=no)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result(show)):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--names", "FOO", "--names", "ABSENT"],
        )
    assert result.exit_code == 0, result.output
    assert "FOO" in result.output and "ABSENT" in result.output
    out = result.output
    foo_line = next(line for line in out.splitlines() if "FOO" in line)
    absent_line = next(line for line in out.splitlines() if "ABSENT" in line)
    assert foo_line != absent_line  # one true, one false — values themselves never appear
    assert "=1" not in out


def test_env_names_unparsed_line_reports_line_number_only(runner, tmp_path):
    env = tmp_path / "svc.env"
    env.write_text("FOO=1\nthis line has no key and might carry a value\nBAR=2\n")
    show = f"{env} (ignore_errors=no)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result(show)):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc"])
    assert result.exit_code == 0, result.output
    assert "2" in result.output  # the unparsed line number is reported…
    assert "this line has no key" not in result.output  # …but never its text


def test_env_names_no_declared_no_fallback_fails(runner, tmp_path):
    with (
        mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result("")),
        mock.patch("aitbc_cli.commands.system.Path.exists", return_value=False),
    ):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-nosuch"])
    assert result.exit_code != 0
    assert "no EnvironmentFile" in result.output


def test_env_names_conventional_fallback(runner, tmp_path):
    """No declared EnvironmentFiles -> the conventional /etc/aitbc/<unit>.env is used."""
    env = tmp_path / "aitbc-svc.env"
    env.write_text("FALLBACK_KEY=1\n")
    real_path = system_mod.Path

    def fake_path(arg):
        return tmp_path if arg == "/etc/aitbc" else real_path(arg)

    with (
        mock.patch.object(system_mod, "_unit_env_files", return_value=[]),
        mock.patch.object(system_mod, "Path", side_effect=fake_path),
    ):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc"])
    assert result.exit_code == 0, result.output
    assert "FALLBACK_KEY" in result.output


def test_env_names_names_are_case_sensitive(runner, tmp_path):
    """--names must report each name exactly as given — never uppercased.

    ``foo`` is set while ``FOO`` is not: an uppercasing implementation would
    invert both answers.
    """
    env = tmp_path / "svc.env"
    env.write_text("foo=1\n")
    show = f"{env} (ignore_errors=no)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", return_value=_systemctl_result(show)):
        result = runner.invoke(
            system,
            obj={"output_format": "json"},
            args=["env-names", "--service", "aitbc-svc", "--names", "foo", "--names", "FOO"],
        )
    assert result.exit_code == 0, result.output
    reported = json.loads(result.output)
    assert reported == {"FOO": False, "foo": True}


# ------------------------------------------------------- env-names --process
#
# All fixtures are invented for the test — no real env name or value is used.


def _systemctl_dispatch(envfiles: str = "", mainpid: str = "4242", active_enter: str = "Sun 2026-10-18 10:50:00 UTC"):
    """Mock ``subprocess.run`` answering both ``systemctl show`` shapes env-names uses."""

    def _run(cmd, **kwargs):
        if "MainPID,ActiveEnterTimestamp" in cmd:
            return _systemctl_result(f"{mainpid}\n{active_enter}\n")
        if "EnvironmentFiles" in cmd:
            return _systemctl_result(envfiles)
        return _systemctl_result("")

    return _run


def _fake_proc(tmp_path, monkeypatch, environ: bytes | None, pid: str = "4242"):
    """Point _PROC_ROOT at a tmp tree; ``environ=None`` leaves the file absent."""
    monkeypatch.setattr(system_mod, "_PROC_ROOT", tmp_path)
    if environ is not None:
        proc_dir = tmp_path / pid
        proc_dir.mkdir()
        (proc_dir / "environ").write_bytes(environ)


def test_env_names_process_names_only(runner, tmp_path, monkeypatch):
    _fake_proc(tmp_path, monkeypatch, b"PROC_ONLY_FLAG=1\x00SHARED_NAME=x\x00")
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "json"},
            args=["env-names", "--service", "aitbc-svc", "--process"],
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["source"] == "process"
    assert data["main_pid"] == 4242
    assert data["active_enter_timestamp"]
    assert data["names"] == ["PROC_ONLY_FLAG", "SHARED_NAME"]
    # values never print — the fake values must not appear anywhere
    assert "=1" not in result.output and "SHARED_NAME=x" not in result.output


def test_env_names_process_names_filter_and_drift(runner, tmp_path, monkeypatch):
    _fake_proc(tmp_path, monkeypatch, b"IN_PROC=1\x00")
    env = tmp_path / "svc.env"
    env.write_text("IN_FILE=1\nIN_PROC=1\n")
    show = f"{env} (ignore_errors=no)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch(envfiles=show)):
        result = runner.invoke(
            system,
            obj={"output_format": "json"},
            args=[
                "env-names",
                "--service",
                "aitbc-svc",
                "--process",
                "--names",
                "IN_PROC",
                "--names",
                "IN_FILE",
                "--names",
                "ABSENT",
            ],
        )
    assert result.exit_code == 0, result.output
    names = json.loads(result.output)["names"]
    assert names["IN_PROC"] == {"set": True}
    assert names["IN_FILE"] == {"set": False, "drift": "declared_only"}
    assert names["ABSENT"] == {"set": False}


def test_env_names_process_full_drift_lists(runner, tmp_path, monkeypatch):
    _fake_proc(tmp_path, monkeypatch, b"ONLY_PROC=1\x00BOTH=1\x00")
    env = tmp_path / "svc.env"
    env.write_text("ONLY_FILE=1\nBOTH=1\n")
    show = f"{env} (ignore_errors=no)\n"
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch(envfiles=show)):
        result = runner.invoke(
            system,
            obj={"output_format": "json"},
            args=["env-names", "--service", "aitbc-svc", "--process"],
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["process_only"] == ["ONLY_PROC"]
    assert data["declared_only"] == ["ONLY_FILE"]


def test_env_names_process_value_allowed(runner, tmp_path, monkeypatch):
    _fake_proc(tmp_path, monkeypatch, b"PLAIN_FLAG=testvalue123\x00")
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--process", "--value", "PLAIN_FLAG"],
        )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "testvalue123"


def test_env_names_process_value_denied_name(runner, tmp_path, monkeypatch, capsys):
    _fake_proc(tmp_path, monkeypatch, b"FAKE_PRIVATE_KEY=shouldneverappear\x00")
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--process", "--value", "FAKE_PRIVATE_KEY"],
        )
    assert result.exit_code != 0
    assert "deny-listed" in result.output
    # the refusal names the rule, never the value
    assert "shouldneverappear" not in result.output
    assert "shouldneverappear" not in capsys.readouterr().out


def test_env_names_process_value_over_cap_refused(runner, tmp_path, monkeypatch):
    _fake_proc(tmp_path, monkeypatch, b"LONG_FLAG=" + b"a" * 250 + b"\x00")
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--process", "--value", "LONG_FLAG"],
        )
    assert result.exit_code != 0
    assert "200" in result.output
    assert "a" * 250 not in result.output


def test_env_names_process_value_requires_process(runner):
    result = runner.invoke(
        system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc", "--value", "X"]
    )
    assert result.exit_code != 0
    assert "requires --process" in result.output


# --- --value deny rules (TOOL-MCP-2 follow-up) ------------------------------
# Secret-class names refused by the token/suffix/tail rules — names only,
# never a live service (the /proc root is faked under tmp_path throughout).


@pytest.mark.parametrize(
    "denied_name",
    [
        "DB_PASSWORD",
        "GOVERNANCE_DB_PASS",
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_SECRET",
        "ADMIN_TOKEN",
        "WALLET_PASSWORD",
        "PGPASSWORD",
        "KEYSTORE_PASSWORD",
        "BRIDGE_AUTHORITY_SECRET",
        "MASTER_PASSPHRASE",
        "VALIDATOR_KEYS",
        "COORDINATOR_API_KEY",
        "BRIDGE_VALIDATOR_PRIVATE_KEY",
        # separator-insensitive / camelCase spellings of the same classes
        "databaseUrl",
        "pg_password",
        "walletPassphrase",
        "dbPasswd",
    ],
)
def test_env_names_process_value_denied_secret_names(runner, tmp_path, monkeypatch, capsys, denied_name):
    _fake_proc(tmp_path, monkeypatch, f"{denied_name}=shouldneverappear\x00".encode())
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--process", "--value", denied_name],
        )
    assert result.exit_code != 0, denied_name
    assert "refused" in result.output.lower() or "denied" in result.output.lower()
    # the refusal names the rule or the variable name, never the value
    assert "shouldneverappear" not in result.output
    assert "shouldneverappear" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "allowed_name, value",
    [
        ("CHAIN_ID", "bc-2"),
        ("LOG_LEVEL", "INFO"),
        ("SYNC_INTERVAL", "30"),
        ("BRIDGE_ROOT_SHADOW_CHECK", "1"),
        ("PROPOSER_ID", "0x" + "ab" * 20),
        ("VALIDATOR_SET", "0x" + "ab" * 20 + ",0x" + "cd" * 20),
        ("pubkey", "0xAbC123"),
        ("monkey", "business"),
        ("keynote", "speaker"),
        ("PLAIN_FLAG", "testvalue123"),
    ],
)
def test_env_names_process_value_allowed_names(runner, tmp_path, monkeypatch, allowed_name, value):
    _fake_proc(tmp_path, monkeypatch, f"{allowed_name}={value}\x00".encode())
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--process", "--value", allowed_name],
        )
    assert result.exit_code == 0, f"{allowed_name}: {result.output}"
    assert result.output.strip() == value


@pytest.mark.parametrize(
    "secret_value",
    [
        # URL carrying user:password
        "postgres://aitbc:hunter2@db.internal/aitbc",
        # 0x + 64 hex — private-key shape
        "0x" + "ab" * 32,
        # bare 64-hex run
        "ab" * 32,
        # 40+ char base64 run
        "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0",
        # three-part dotted token (JWT shape)
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6y",
    ],
)
def test_env_names_process_value_secret_shaped(runner, tmp_path, monkeypatch, capsys, secret_value):
    _fake_proc(tmp_path, monkeypatch, f"PLAIN_FLAG={secret_value}\x00".encode())
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--process", "--value", "PLAIN_FLAG"],
        )
    assert result.exit_code != 0
    assert "refused" in result.output.lower()
    assert secret_value not in result.output
    assert secret_value not in capsys.readouterr().out


# --- plural/short deny spellings (GAP-ENVDENY-2) -----------------------------
# Residual spellings the token-equality guard missed: plurals, the short
# form PW, and compound words. "pw" is token-only — never a suffix — so
# CREW/FLOW stay allowed. "authorization" is single-token-suffix only so
# bare AUTHORIZATION refuses while the live flag ENABLE_AUTHORIZATION stays
# allowed. "keyfile" is deliberately allowed: it names a path to key
# material, not the secret itself — same class as the required-allow
# KEYSTORE_DIR.


@pytest.mark.parametrize(
    "denied_name",
    [
        "DB_PW",
        "ADMIN_PW",
        "PW",
        "SECRETS",
        "PASSWORDS",
        "TOKENS",
        "APIKEYS",
        "HMAC_SECRETS",
        "AUTHORIZATION",
        "BEARER",
        "COOKIE",
        "COOKIES",
        "SESSION_COOKIE",
        "PRIVKEY",
        "SEEDPHRASE",
        "SALT",
        # separator-less spellings caught by the single-token suffix rule
        "MYAUTHORIZATION",
        "ETHPRIVKEY",
        "MYSEEDPHRASE",
        "MYSECRETS",
    ],
)
def test_env_names_process_value_denied_plural_short_names(runner, tmp_path, monkeypatch, capsys, denied_name):
    _fake_proc(tmp_path, monkeypatch, f"{denied_name}=shouldneverappear\x00".encode())
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--process", "--value", denied_name],
        )
    assert result.exit_code != 0, denied_name
    assert "shouldneverappear" not in result.output
    assert "shouldneverappear" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "allowed_name",
    [
        # must-allow names from the first round, still allowed
        "KEYSTORE_DIR",
        "SUPPORTED_CHAINS",
        # "pw" is a token only, not a suffix: unrelated endings survive
        "CREW_COUNT",
        "FLOW_RATE",
        # "salt" is a token only: unrelated containing tokens survive
        "RESULT_FILE",
        # live fleet flag: "authorization" is not a plain deny token
        "ENABLE_AUTHORIZATION",
        # a keyfile value is a path, not the secret — same class as
        # KEYSTORE_DIR above
        "ETH_KEYFILE",
        "COOKIELESS",
    ],
)
def test_env_names_process_value_allowed_residual_names(runner, tmp_path, monkeypatch, allowed_name):
    _fake_proc(tmp_path, monkeypatch, f"{allowed_name}=safevalue\x00".encode())
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "table"},
            args=["env-names", "--service", "aitbc-svc", "--process", "--value", allowed_name],
        )
    assert result.exit_code == 0, f"{allowed_name}: {result.output}"
    assert result.output.strip() == "safevalue"


def test_env_names_denied_guard_allows_all_fleet_names():
    """Every env name the fleet currently relies on stays allowed.

    Fixture: cli/tests/fixtures/fleet_env_names_allowed.txt — the 246 distinct
    names the guard allowed across the five hosts' /etc/aitbc/*.env files
    on 20 Oct 2026 (names only, no values; director's census). A deny
    token that trips a legitimate fleet name fails here.
    """
    fixture = Path(__file__).parent / "fixtures" / "fleet_env_names_allowed.txt"
    names = [line.strip() for line in fixture.read_text().splitlines() if line.strip()]
    assert len(names) == 246  # fixture drift guard
    refused = [name for name in names if system_mod._field_name_denied(name)]
    assert refused == []


def test_file_info_field_secret_shaped_value_refused(runner, allowed, capsys):
    secret = "0x" + "ab" * 32
    f = _write_json(allowed / "node.json", {"note": secret})
    result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", "note"])
    assert result.exit_code != 0
    assert "refused" in result.output.lower()
    assert secret not in capsys.readouterr().out


def test_file_info_field_denied_token_names_refused(runner, allowed, capsys):
    secret = "0xSECRETNEVERPRINTED123"
    f = _write_json(
        allowed / "node.json",
        {"db_password": secret, "database_url": secret, "master_passphrase": secret, "pgpassword": secret},
    )
    for denied in ("db_password", "database_url", "master_passphrase", "pgpassword"):
        result = runner.invoke(system, obj={"output_format": "table"}, args=["file-info", "--path", str(f), "--field", denied])
        assert result.exit_code != 0, denied
    assert secret not in capsys.readouterr().out


def test_env_names_process_not_running(runner, tmp_path, monkeypatch):
    _fake_proc(tmp_path, monkeypatch, None)
    with mock.patch(
        "aitbc_cli.commands.system.subprocess.run",
        side_effect=_systemctl_dispatch(mainpid="0", active_enter=""),
    ):
        result = runner.invoke(
            system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc", "--process"]
        )
    assert result.exit_code != 0
    assert "not running" in result.output
    assert "Traceback" not in result.output


def test_env_names_process_environ_gone(runner, tmp_path, monkeypatch):
    _fake_proc(tmp_path, monkeypatch, None)  # environ file absent
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc", "--process"]
        )
    assert result.exit_code != 0
    assert "vanished" in result.output
    assert "Traceback" not in result.output


def test_env_names_process_unreadable_environ(runner, tmp_path, monkeypatch):
    _fake_proc(tmp_path, monkeypatch, b"X=1\x00")
    environ = tmp_path / "4242" / "environ"
    real_read_bytes = system_mod.Path.read_bytes

    def denied(self):
        if self == environ:
            raise PermissionError(13, "Permission denied")
        return real_read_bytes(self)

    with (
        mock.patch.object(system_mod.Path, "read_bytes", denied),
        mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()),
    ):
        result = runner.invoke(
            system, obj={"output_format": "table"}, args=["env-names", "--service", "aitbc-svc", "--process"]
        )
    assert result.exit_code != 0
    assert "permission denied" in result.output.lower()
    assert "Traceback" not in result.output


def test_env_names_process_works_without_env_files(runner, tmp_path, monkeypatch):
    """A unit declaring no EnvironmentFile still reports its process names."""
    _fake_proc(tmp_path, monkeypatch, b"ONLY_PROC=1\x00")
    with mock.patch("aitbc_cli.commands.system.subprocess.run", side_effect=_systemctl_dispatch()):
        result = runner.invoke(
            system,
            obj={"output_format": "json"},
            args=["env-names", "--service", "aitbc-svc", "--process"],
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["names"] == ["ONLY_PROC"]
    assert data["process_only"] == ["ONLY_PROC"]


def test_env_names_help_lists_denylist(runner):
    """--value refusals follow the same generated deny epilog as file-info."""
    result = runner.invoke(system, args=["env-names", "--help"])
    assert result.exit_code == 0, result.output
    for token in ("private_key", "mnemonic", "_key", "200"):
        assert token in result.output, token


def test_file_info_help_lists_denylist(runner):
    """CLI-7 row 37: --help epilog is generated from the denylist constants,
    so the documented refused names cannot drift from the code."""
    result = runner.invoke(system, args=["file-info", "--help"])
    assert result.exit_code == 0, result.output
    for token in (
        # one name per denylist category, straight from the constants
        "private_key",
        "mnemonic",
        "_key",
        "passphrase",
        "credentials",
        "privatekey",
        "private/secret/api/auth/signing/access",
        "200",
    ):
        assert token in result.output, token
