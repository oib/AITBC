"""Pin for AUDIT-EDGE-CLI-GOV-SERVICE-KEY (#2885).

``_service_env_api_key`` silently adopted GOVERNANCE_API_KEY from
/etc/aitbc/aitbc-governance.env with no permission/ownership check —
any local user running `aitbc governance <mutating>` got admin API calls
for free. The file must now be 0600-ish (no group/other bits) and owned
by the caller or readable-as-root, matching the island_credentials bar.
"""

from aitbc_cli.commands import governance as gov


def _env_file(tmp_path, mode=0o600, content="GOVERNANCE_API_KEY=svc-key-123\nOTHER=x\n"):
    p = tmp_path / "aitbc-governance.env"
    p.write_text(content)
    p.chmod(mode)
    return p


def test_tight_perms_adopts_key(tmp_path, monkeypatch):
    p = _env_file(tmp_path)
    monkeypatch.setattr(gov, "_GOVERNANCE_ENV_FILE", p)
    assert gov._service_env_api_key() == "svc-key-123"


def test_group_or_world_readable_refused(tmp_path, monkeypatch, caplog):
    for mode in (0o640, 0o644, 0o604, 0o660):
        p = _env_file(tmp_path, mode=mode)
        monkeypatch.setattr(gov, "_GOVERNANCE_ENV_FILE", p)
        assert gov._service_env_api_key() is None, f"mode {oct(mode)} adopted the service key"


def test_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(gov, "_GOVERNANCE_ENV_FILE", tmp_path / "nope.env")
    assert gov._service_env_api_key() is None


def test_no_key_line_returns_none(tmp_path, monkeypatch):
    p = _env_file(tmp_path, content="OTHER=x\n")
    monkeypatch.setattr(gov, "_GOVERNANCE_ENV_FILE", p)
    assert gov._service_env_api_key() is None
