"""Pins for scripts/utils/security_hardening.sh (SECURITY-HARDENING-API-KEY-BRACKETS-1, #934).

The script used to write API keys as JSON lists into api_keys.txt, ``source``
that file (bash strips the quotes), and sed ``[key]`` literals into
.env.production — a key the coordinator's comma fallback stores *with*
brackets, so the documented key never authenticates. The env update now writes
the shell variables directly, the settings block appends once, check_root runs
before any mkdir, and the summary names the real cron log path. The script is
sourced (``BASH_SOURCE`` guard) with its path variables overridden, so the
functions run against tmp dirs only.
"""

import json
import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "utils" / "security_hardening.sh"

CLIENT = "a" * 32
MINER = "b" * 32
ADMIN = "c" * 32
WALLET_PW = "d" * 64


def _bash(tmp_path: Path, body: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(
        {
            "PRODUCTION_ENV": str(tmp_path / "env.production"),
            "SECURE_DIR": str(tmp_path / "secure"),
            "BLOCKCHAIN_SECRETS_ENV": str(tmp_path / "etc" / "blockchain-secrets.env"),
            "LOG_FILE": str(tmp_path / "hardening.log"),
        }
    )
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"\n{body}'],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _env(tmp_path: Path) -> Path:
    env_file = tmp_path / "env.production"
    env_file.write_text(
        'CLIENT_API_KEYS=["oldclient"]\n'
        'MINER_API_KEYS=["oldminer","oldminer2"]\n'
        'ADMIN_API_KEYS=["oldadmin"]\n'
        "ENV=development\n"
    )
    return env_file


def test_api_keys_land_as_valid_json_lists(tmp_path):
    env_file = _env(tmp_path)
    proc = _bash(
        tmp_path,
        f"CLIENT_KEY={CLIENT} MINER_KEY={MINER} ADMIN_KEY={ADMIN} WALLET_IMPORT_PASSWORD={WALLET_PW} update_production_env",
    )
    assert proc.returncode == 0, proc.stderr

    lines = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line and not line.startswith("#"))
    for key, want in (("CLIENT_API_KEYS", [CLIENT]), ("MINER_API_KEYS", [MINER]), ("ADMIN_API_KEYS", [ADMIN])):
        parsed = json.loads(lines[key])
        assert parsed == want
        # The bracket-literal bug: the stored value must not contain '[' inside a key.
        assert all(k == k.strip("[]") for k in parsed)


def test_settings_block_is_idempotent_and_upsert_appends_missing_keys(tmp_path):
    env_file = _env(tmp_path)
    env_file.write_text("ENV=development\n")  # no key lines at all
    body = f"CLIENT_KEY={CLIENT} MINER_KEY={MINER} ADMIN_KEY={ADMIN} WALLET_IMPORT_PASSWORD= update_production_env"
    proc = _bash(tmp_path, body)
    assert proc.returncode == 0, proc.stderr
    first = env_file.read_text()
    assert first.count("# Production Security Settings") == 1
    assert f'CLIENT_API_KEYS=["{CLIENT}"]' in first

    proc = _bash(tmp_path, body)
    assert proc.returncode == 0, proc.stderr
    assert env_file.read_text() == first
    assert env_file.read_text().count("# Production Security Settings") == 1


def test_wallet_password_goes_to_secrets_env_not_production(tmp_path):
    env_file = _env(tmp_path)
    proc = _bash(
        tmp_path,
        f"CLIENT_KEY={CLIENT} MINER_KEY={MINER} ADMIN_KEY={ADMIN} WALLET_IMPORT_PASSWORD={WALLET_PW} update_production_env",
    )
    assert proc.returncode == 0, proc.stderr
    secrets = tmp_path / "etc" / "blockchain-secrets.env"
    assert f"WALLET_IMPORT_PASSWORD={WALLET_PW}" in secrets.read_text().splitlines()
    assert "WALLET_IMPORT_PASSWORD" not in env_file.read_text()
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o600


def test_generate_api_keys_writes_record_file(tmp_path):
    proc = _bash(tmp_path, "generate_api_keys")
    assert proc.returncode == 0, proc.stderr
    keys_file = tmp_path / "secure" / "api_keys.txt"
    assert keys_file.exists()
    assert stat.S_IMODE(keys_file.stat().st_mode) == 0o600
    text = keys_file.read_text()
    client_line = next(line for line in text.splitlines() if line.startswith("CLIENT_API_KEYS="))
    assert len(json.loads(client_line.split("=", 1)[1])) == 1
    assert len(json.loads(client_line.split("=", 1)[1])[0]) == 32


def test_summary_names_the_real_cron_log():
    text = SCRIPT.read_text()
    assert "/var/log/aitbc/health_check_cron.log" in text
    assert "/var/log/aitbc-health.log" not in text


def test_check_root_runs_before_mkdir():
    text = SCRIPT.read_text()
    main_body = text[text.index("main() {") : text.index('if [[ "${BASH_SOURCE[0]}"')]
    assert main_body.index("check_root") < main_body.index("mkdir -p")
