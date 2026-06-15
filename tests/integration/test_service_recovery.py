"""Integration tests for AITBC service recovery infrastructure.

Validates that the systemd recovery unit, secret-loading script,
and deployment integration work together to restore service state
after a reboot.
"""

import configparser
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RECOVERY_SERVICE = REPO_ROOT / "scripts" / "systemd" / "aitbc-recovery.service"
LOAD_SECRETS = REPO_ROOT / "scripts" / "utils" / "load-keystore-secrets.sh"
LINK_SYSTEMD = REPO_ROOT / "scripts" / "utils" / "link-systemd.sh"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deployment" / "deploy.sh"


class TestRecoveryFilesExist:
    """Ensure all recovery artifacts are present in the repository."""

    def test_recovery_service_file_exists(self) -> None:
        assert RECOVERY_SERVICE.is_file(), f"Missing {RECOVERY_SERVICE}"

    def test_load_keystore_secrets_script_exists(self) -> None:
        assert LOAD_SECRETS.is_file(), f"Missing {LOAD_SECRETS}"

    def test_link_systemd_script_exists(self) -> None:
        assert LINK_SYSTEMD.is_file(), f"Missing {LINK_SYSTEMD}"

    def test_deploy_script_exists(self) -> None:
        assert DEPLOY_SCRIPT.is_file(), f"Missing {DEPLOY_SCRIPT}"


class TestRecoveryServiceUnitFile:
    """Validate the aitbc-recovery.service systemd unit."""

    @pytest.fixture(scope="class")
    def unit(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        parser.read(RECOVERY_SERVICE)
        return parser

    def test_has_unit_section(self, unit: configparser.ConfigParser) -> None:
        assert unit.has_section("Unit")

    def test_has_service_section(self, unit: configparser.ConfigParser) -> None:
        assert unit.has_section("Service")

    def test_has_install_section(self, unit: configparser.ConfigParser) -> None:
        assert unit.has_section("Install")

    def test_before_core_services(self, unit: configparser.ConfigParser) -> None:
        before = unit.get("Unit", "Before", fallback="")
        assert "aitbc-blockchain-node.service" in before
        assert "aitbc-coordinator-api.service" in before
        assert "aitbc-marketplace.service" in before

    def test_type_oneshot(self, unit: configparser.ConfigParser) -> None:
        assert unit.get("Service", "Type", fallback="") == "oneshot"

    def test_exec_start_calls_both_scripts(self, unit: configparser.ConfigParser) -> None:
        exec_start = unit.get("Service", "ExecStart", fallback="")
        assert "link-systemd.sh" in exec_start
        assert "load-keystore-secrets.sh" in exec_start

    def test_remain_after_exit(self, unit: configparser.ConfigParser) -> None:
        assert unit.get("Service", "RemainAfterExit", fallback="") == "yes"

    def test_wanted_by_multi_user(self, unit: configparser.ConfigParser) -> None:
        wanted_by = unit.get("Install", "WantedBy", fallback="")
        assert "multi-user.target" in wanted_by


class TestScriptSyntax:
    """Ensure shell scripts are syntactically valid."""

    def test_link_systemd_script_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(LINK_SYSTEMD)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in {LINK_SYSTEMD}: {result.stderr}"

    def test_load_keystore_secrets_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(LOAD_SECRETS)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in {LOAD_SECRETS}: {result.stderr}"


class TestDeployIntegration:
    """Verify deploy.sh invokes the secret-loading step."""

    def test_deploy_calls_load_keystore_secrets(self) -> None:
        content = DEPLOY_SCRIPT.read_text()
        assert "load-keystore-secrets.sh" in content
        assert "setup_systemd_services" in content


class TestSecretLoading:
    """End-to-end secret-loading in a temporary environment."""

    @pytest.fixture
    def fake_creds(self) -> Path:
        with tempfile.TemporaryDirectory() as tmp:
            creds_dir = Path(tmp) / "credentials"
            creds_dir.mkdir()

            # Create plaintext secrets
            (creds_dir / "api_hash_secret").write_text("super-secret-hash")
            (creds_dir / "proposer_id").write_text("node-42")
            (creds_dir / "keystore_password").write_text("keystore-pass")

            # Create a PostgreSQL password
            (creds_dir / "postgres_aitbc_user_password").write_text("db-pass")

            # Version file
            (creds_dir / "api_hash_secret.version").write_text("3")

            yield creds_dir

    @pytest.fixture
    def patched_script(self) -> Path:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            script_copy = tmp_path / "load-keystore-secrets.sh"
            script_copy.write_text(LOAD_SECRETS.read_text())
            yield script_copy

    def test_load_secrets_creates_env_file(self, fake_creds: Path, patched_script: Path) -> None:
        run_dir = Path(tempfile.mkdtemp())
        audit_log = run_dir / "audit.log"

        # Rewrite hardcoded paths in temp script copy
        content = patched_script.read_text()
        content = content.replace(
            'CREDENTIALS_DIR="/etc/aitbc/credentials"',
            f'CREDENTIALS_DIR="{fake_creds}"',
        )
        content = content.replace(
            'RUN_DIR="/run/aitbc/secrets"',
            f'RUN_DIR="{run_dir}"',
        )
        content = content.replace(
            'AUDIT_LOG="/var/log/aitbc/secrets-audit.log"',
            f'AUDIT_LOG="{audit_log}"',
        )
        content = content.replace(
            'ENCRYPTION_KEY_FILE="/etc/aitbc/credentials/encryption_key"',
            f'ENCRYPTION_KEY_FILE="{run_dir}/encryption_key"',
        )
        patched_script.write_text(content)

        result = subprocess.run(
            ["bash", str(patched_script)],
            capture_output=True,
            text=True,
        )

        # The script may exit non-zero if it can't write to /var/log,
        # but we only care that the .env file is produced
        env_file = run_dir / ".env"
        assert env_file.is_file(), f".env file not created. stdout={result.stdout} stderr={result.stderr}"

        env_content = env_file.read_text()
        assert "API_KEY_HASH_SECRET=super-secret-hash" in env_content
        assert "proposer_id=node-42" in env_content
        assert "KEYSTORE_PASSWORD=keystore-pass" in env_content
        assert "POSTGRES_AITBC_USER_PASSWORD=db-pass" in env_content

    def test_load_secrets_audit_log(self, fake_creds: Path, patched_script: Path) -> None:
        run_dir = Path(tempfile.mkdtemp())
        audit_log = run_dir / "audit.log"

        content = patched_script.read_text()
        content = content.replace(
            'CREDENTIALS_DIR="/etc/aitbc/credentials"',
            f'CREDENTIALS_DIR="{fake_creds}"',
        )
        content = content.replace(
            'RUN_DIR="/run/aitbc/secrets"',
            f'RUN_DIR="{run_dir}"',
        )
        content = content.replace(
            'AUDIT_LOG="/var/log/aitbc/secrets-audit.log"',
            f'AUDIT_LOG="{audit_log}"',
        )
        content = content.replace(
            'ENCRYPTION_KEY_FILE="/etc/aitbc/credentials/encryption_key"',
            f'ENCRYPTION_KEY_FILE="{run_dir}/encryption_key"',
        )
        patched_script.write_text(content)

        subprocess.run(
            ["bash", str(patched_script)],
            capture_output=True,
            text=True,
        )

        assert audit_log.is_file()
        log_text = audit_log.read_text()
        assert "LOAD" in log_text
        assert "api_hash_secret" in log_text
        assert "version 3" in log_text

    def test_env_file_permissions(self, fake_creds: Path, patched_script: Path) -> None:
        run_dir = Path(tempfile.mkdtemp())
        audit_log = run_dir / "audit.log"

        content = patched_script.read_text()
        content = content.replace(
            'CREDENTIALS_DIR="/etc/aitbc/credentials"',
            f'CREDENTIALS_DIR="{fake_creds}"',
        )
        content = content.replace(
            'RUN_DIR="/run/aitbc/secrets"',
            f'RUN_DIR="{run_dir}"',
        )
        content = content.replace(
            'AUDIT_LOG="/var/log/aitbc/secrets-audit.log"',
            f'AUDIT_LOG="{audit_log}"',
        )
        content = content.replace(
            'ENCRYPTION_KEY_FILE="/etc/aitbc/credentials/encryption_key"',
            f'ENCRYPTION_KEY_FILE="{run_dir}/encryption_key"',
        )
        patched_script.write_text(content)

        subprocess.run(
            ["bash", str(patched_script)],
            capture_output=True,
            text=True,
        )

        env_file = run_dir / ".env"
        assert env_file.is_file()
        # Script sets chmod 600 on the .env file
        mode = env_file.stat().st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got 0o{mode:o}"
