"""Pin for AUDIT-EDGE-MCP-SHOW-SECRETS (#2880), CLI half.

``aitbc system config`` hides secret values unless ``--show-secrets`` — but
the hide filter was a naive substring check for key/secret/password/token,
so ``AITBC_JWT``, ``*_JWT``, and secret-shaped values under innocuous names
printed raw. The filter now uses the shared ``_field_name_denied`` table
(just extended with the ``jwt`` token) plus ``_field_value_shape_denied``.
"""

from pathlib import Path

import pytest

from aitbc_cli.commands import system as system_mod


ENV_BODY = """\
# comment line
AITBC_JWT_SECRET=jwt-secret-value-123
API_KEY=shortkey
NODE_URL=http://hub.example:8202
PROPOSER_ID=0xE8948a556E8F2317d255b5d5021f2CECcBBd9CE2
DATABASE_URL=postgres://user:passw0rd@db.internal:5432/aitbc
INNOCUOUS_NAME=just-a-value
EMPTY_LINE=
"""


def _invoke_config(runner, monkeypatch, tmp_path, *args):
    env_file = tmp_path / "blockchain.env"
    env_file.write_text(ENV_BODY)
    real_path = Path(env_file)
    # config() hardcodes Path("/etc/aitbc/blockchain.env"); redirect the
    # module-level Path lookup for the duration of the call.
    monkeypatch.setattr(system_mod, "Path", lambda *a, **k: real_path)
    return runner.invoke(system_mod.system, ["config", *args], obj={"output_format": "table"})


def test_config_hides_denylisted_and_secret_shaped_values(runner, monkeypatch, tmp_path):
    result = _invoke_config(runner, monkeypatch, tmp_path)
    assert result.exit_code == 0, result.output
    out = result.output
    # Deny-name hits: jwt token, key suffix.
    assert "jwt-secret-value-123" not in out
    assert "shortkey" not in out
    # Value-shape hit under a conn-string name (user:pass@ URL).
    assert "passw0rd" not in out
    # Innocuous values stay visible.
    assert "http://hub.example:8202" in out
    assert "just-a-value" in out
    assert "0xE8948a556E8F2317d255b5d5021f2CECcBBd9CE2" in out


def test_config_show_secrets_still_prints(runner, monkeypatch, tmp_path):
    result = _invoke_config(runner, monkeypatch, tmp_path, "--show-secrets")
    assert result.exit_code == 0, result.output
    assert "jwt-secret-value-123" in result.output
    assert "shortkey" in result.output


def test_jwt_is_a_deny_token():
    assert system_mod._field_name_denied("AITBC_JWT_SECRET")
    assert system_mod._field_name_denied("JWT_TOKEN")
    # Token-level denial covers the whole JWT_* family — safe direction for
    # env-set/file paths; config display hides the value either way.
    assert system_mod._field_name_denied("JWT_ISSUER")
