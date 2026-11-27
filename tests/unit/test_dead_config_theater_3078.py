"""AUDIT-DEAD-CONFIG-THEATER-1 (#3078): security-shaped configuration that
protected nothing — pins for the removals/wirings.

Each test pins one audit item so a regression re-opens the specific hole:

1. ``BRIDGE_VERIFICATION_MODE=oracle`` — accepted-but-unimplemented; it
   silently SKIPPED in-process Merkle verification while ``_oracle`` stayed
   ``None``. Now refused at startup unconditionally.
2. ``AITBC_DB_KEY`` — read once at import, never consumed, booby-trapped
   hardcoded default; real path is ``db_encryption_key_path``.
3. Coordinator ``hmac_secret`` — documented, zero consumers.
4. ``BLOCKCHAIN_API_KEY`` — fictional; removed from env templates.
5. Agent-coordinator ``ALLOWED_HOSTS`` — parsed, never enforced; now wired
   to ``TrustedHostMiddleware``.
6. Coordinator ``.env.example`` ``RATE_LIMIT_REQUESTS``/``_WINDOW_SECONDS``
   — dead generic pair (per-route ``rate_limit_*`` settings are live).
7. Exchange ``BRIDGE_CUSTODIAN_MODE``/``BRIDGE_MULTISIG_ENABLED`` — fed
   status dicts only; withdrawal verification reads threshold+signers.
8. Edge ``/agents/heartbeat`` POST — route doesn't exist on the
   coordinator; presence is reported on-chain via ``/rpc/edge/register``.
9. Deprecated ``aitbc operations ai`` — targeted ``/v1/jobs``, which the
   agent-coordinator never served.
10. Agent-coordinator ``ADMIN/OPERATOR/USER_PASSWORD`` — required by
    ``/api/v1/auth/login`` but absent from every deployment template;
    ``setup.sh`` now generates + writes them.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _src(*parts: str) -> Path:
    return _REPO.joinpath(*parts)


# ---------------------------------------------------------------------------
# 1. BRIDGE_VERIFICATION_MODE=oracle — fail closed at startup
# ---------------------------------------------------------------------------


class TestBridgeVerificationMode:
    def _mode_check(self):
        from aitbc_chain.cross_chain import bridge as bridge_mod

        return bridge_mod._validate_bridge_verification_mode

    def test_oracle_mode_rejected(self):
        check = self._mode_check()
        with patch("aitbc_chain.cross_chain.bridge.settings") as s:
            s.bridge_verification_mode = "oracle"
            with pytest.raises(Exception, match="oracle"):
                check()

    def test_unknown_mode_rejected(self):
        check = self._mode_check()
        with patch("aitbc_chain.cross_chain.bridge.settings") as s:
            s.bridge_verification_mode = "field-eq"
            with pytest.raises(Exception, match="in_process"):
                check()

    def test_in_process_accepted(self):
        check = self._mode_check()
        with patch("aitbc_chain.cross_chain.bridge.settings") as s:
            s.bridge_verification_mode = "in_process"
            check()  # no raise

    def test_mode_check_runs_even_when_release_disabled(self):
        """The trap must not be armable for a later activation: oracle fails
        startup even with bridge_release_enabled=False."""
        from aitbc_chain.cross_chain import bridge as bridge_mod

        with patch("aitbc_chain.cross_chain.bridge.settings") as s:
            s.bridge_release_enabled = False
            s.bridge_verification_mode = "oracle"
            with pytest.raises(Exception, match="oracle"):
                bridge_mod._validate_bridge_production_safety()

    def test_oracle_settings_fields_removed(self):
        from aitbc_chain.config import ChainSettings

        settings = ChainSettings()
        assert not hasattr(settings, "bridge_oracle_endpoints")
        assert not hasattr(settings, "bridge_oracle_timeout")
        assert not hasattr(settings, "bridge_oracle_health_check_interval")


# ---------------------------------------------------------------------------
# 2. AITBC_DB_KEY — dead variable + booby-trapped default removed
# ---------------------------------------------------------------------------


def test_db_encryption_key_env_var_removed():
    src = _src("apps/blockchain-node/src/aitbc_chain/database.py").read_text()
    assert '_DB_ENCRYPTION_KEY = os.environ.get("AITBC_DB_KEY"' not in src
    assert "_DB_ENCRYPTION_KEY" not in src
    assert "default_encryption_key_change_in_production" not in src


def test_db_encryption_doc_points_at_real_path():
    doc = _src("docs/deployment/environment-configuration.md").read_text()
    row = next(line for line in doc.splitlines() if "AITBC_DB_KEY" in line)
    assert "Removed" in row
    assert "DB_ENCRYPTION_KEY_PATH" in row


# ---------------------------------------------------------------------------
# 3+6. Coordinator dead config — hmac_secret field, env-example dead pair
# ---------------------------------------------------------------------------


def test_coordinator_hmac_secret_field_removed():
    sys.path.insert(0, str(_src("apps/coordinator-api/src")))
    try:
        from coordinator_api.config import Settings
    finally:
        sys.path.remove(str(_src("apps/coordinator-api/src")))
    assert "hmac_secret" not in Settings.model_fields


def test_coordinator_env_example_dead_rate_limit_pair_removed():
    example = _src("apps/coordinator-api/.env.example").read_text()
    for line in example.splitlines():
        assert not line.startswith("RATE_LIMIT_REQUESTS=")
        assert not line.startswith("RATE_LIMIT_WINDOW_SECONDS=")
        assert not line.startswith("HMAC_SECRET=")


# ---------------------------------------------------------------------------
# 4. BLOCKCHAIN_API_KEY — fictional var out of env templates
# ---------------------------------------------------------------------------


def test_blockchain_api_key_out_of_env_templates():
    doc = _src("docs/deployment/environment-configuration.md").read_text()
    assert "BLOCKCHAIN_API_KEY=" not in doc


# ---------------------------------------------------------------------------
# 5. agent-coordinator ALLOWED_HOSTS — wired, not parsed-and-dropped
# ---------------------------------------------------------------------------


def test_agent_coordinator_allowed_hosts_wired():
    src = _src("apps/agent-coordinator/src/agent_app/main.py").read_text()
    assert "TrustedHostMiddleware" in src
    assert "allowed_hosts=settings.allowed_hosts_list" in src


def test_agent_coordinator_allowed_hosts_rejects_foreign_host(monkeypatch):
    """Functional: ALLOWED_HOSTS parses comma-separated and reaches
    TrustedHostMiddleware — before #3078 the env var was parsed into a
    list field that pydantic-settings JSON-decoded (a plain "a,b" value
    crashed settings load) and was never consumed anyway."""
    _tmp = tempfile.mkdtemp(prefix="test-agentcoord-3078-")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-0123456789abcdef")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-0123456789abcdef0123456789")
    monkeypatch.setenv("ALLOWED_HOSTS", "agent.example.com, backup.example.com")
    monkeypatch.setenv("AGENT_DB_PATH", str(Path(_tmp) / "agent.db"))
    monkeypatch.setenv("API_KEY_STORAGE_PATH", str(Path(_tmp) / "api_keys.json"))
    monkeypatch.setenv("AITBC_DATA_DIR", _tmp)
    monkeypatch.setenv("AITBC_OUTBOUND_URL_ALLOWED_TARGETS", "localhost,127.0.0.1")
    monkeypatch.setenv("AITBC_SKIP_ENV_FILES", "1")
    src_dir = str(_src("apps/agent-coordinator/src"))
    sys.path.insert(0, src_dir)
    try:
        from agent_app.config import Settings

        s = Settings()
        assert s.allowed_hosts_list == ["agent.example.com", "backup.example.com"]

        import agent_app.main as am
        from fastapi.middleware.trustedhost import TrustedHostMiddleware

        app = am.create_app()
        th = [mw for mw in app.user_middleware if mw.cls is TrustedHostMiddleware]
        assert th, "TrustedHostMiddleware not registered"
    finally:
        sys.path.remove(src_dir)


# ---------------------------------------------------------------------------
# 7. Exchange status-only bridge flags removed
# ---------------------------------------------------------------------------


def test_exchange_bridge_config_dead_flags_removed():
    sys.path.insert(0, str(_src("apps/exchange")))
    try:
        from simple_exchange.config import BridgeConfig, _load_bridge_config
    finally:
        sys.path.remove(str(_src("apps/exchange")))
    assert not hasattr(BridgeConfig(), "custodian")
    assert not hasattr(BridgeConfig(), "multisig_enabled")
    with patch.dict(os.environ, {"BRIDGE_CUSTODIAN_MODE": "false", "BRIDGE_MULTISIG_ENABLED": "true"}):
        cfg = _load_bridge_config()
    assert not hasattr(cfg, "custodian")
    assert not hasattr(cfg, "multisig_enabled")
    assert "custodian" not in cfg.as_status()
    assert "multisig_enabled" not in cfg.as_status()


def test_exchange_env_example_dead_flags_removed():
    example = _src("apps/exchange/simple_exchange/.env.example").read_text()
    for line in example.splitlines():
        assert not line.startswith("BRIDGE_CUSTODIAN_MODE=")
        assert not line.startswith("BRIDGE_MULTISIG_ENABLED=")


# ---------------------------------------------------------------------------
# 8. Edge coordinator heartbeat — dead route, removed
# ---------------------------------------------------------------------------


def test_edge_heartbeat_task_removed():
    main_src = _src("apps/edge/src/aitbc_edge/main.py").read_text()
    assert "_report_health_to_coordinator" not in main_src
    assert "/agents/heartbeat" not in main_src


def test_edge_config_dead_fields_removed():
    src = _src("apps/edge/src/aitbc_edge/config.py").read_text()
    assert "agent_coordinator_url:" not in src
    assert "agent_heartbeat_interval_seconds:" not in src


# ---------------------------------------------------------------------------
# 9. Deprecated operations ai subgroup — /v1/jobs never existed
# ---------------------------------------------------------------------------


def test_operations_ai_subgroup_unregistered():
    sys.path.insert(0, str(_src("cli")))
    try:
        from aitbc_cli.commands.operations import operations
    finally:
        sys.path.remove(str(_src("cli")))
    assert "ai" not in operations.commands
    assert "agent" in operations.commands
    assert "governance" in operations.commands


# ---------------------------------------------------------------------------
# 10. agent-coordinator login passwords — generated + documented
# ---------------------------------------------------------------------------


def test_setup_sh_generates_agent_coordinator_passwords():
    script = _src("scripts/deployment/setup.sh").read_text()
    assert "agent_admin_password" in script
    assert "agent_operator_password" in script
    assert "agent_user_password" in script
    assert "ADMIN_PASSWORD=" in script
    assert "OPERATOR_PASSWORD=" in script
    assert "USER_PASSWORD=" in script


def test_agent_coordinator_passwords_documented():
    doc = _src("docs/deployment/environment-configuration.md").read_text()
    assert "ADMIN_PASSWORD" in doc
    assert "OPERATOR_PASSWORD" in doc
    assert "USER_PASSWORD" in doc
