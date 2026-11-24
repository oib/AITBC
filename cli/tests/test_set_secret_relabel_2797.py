"""AUDIT-EDGE-CLI-SET-SECRET-BASE64 (#2797): ``config set-secret`` stored
secrets as trivially reversible base64 while calling them "encoded" —
users could read that as encrypted. The command now says plainly that the
value is base64-encoded, NOT encrypted.
"""

from pathlib import Path

from click.testing import CliRunner


def test_set_secret_output_says_not_encrypted(monkeypatch, tmp_path):
    from aitbc_cli.commands import config as config_mod

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    result = CliRunner().invoke(config_mod.config, ["set-secret", "--key", "k1", "--value", "v1"])
    assert result.exit_code == 0, result.output
    assert "not encrypted" in result.output
