"""AUDIT-EDGE-CLI-PROFILE-TRAVERSAL (#2794): ``config profiles --name`` was
joined raw into ``~/.config/aitbc/profiles/{name}.yaml`` — ``../../x`` gave
arbitrary ``*.yaml`` write (save), read+config-overwrite (load), and unlink
(delete). Names now go through the wallet-name charset validator.
"""

from pathlib import Path

from click.testing import CliRunner

from aitbc_cli.commands.config import profiles


def _profiles_dir(monkeypatch, tmp_path):
    target = tmp_path / "home" / ".config" / "aitbc" / "profiles"
    target.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return target


def test_save_refuses_traversal_name(monkeypatch, tmp_path):
    prof_dir = _profiles_dir(monkeypatch, tmp_path)
    result = CliRunner().invoke(profiles, ["save", "--name", "../../escape"])
    assert result.exit_code != 0
    assert not (tmp_path / "escape.yaml").exists()
    assert not (tmp_path / "home" / "escape.yaml").exists()
    assert list(prof_dir.glob("*.yaml")) == []


def test_load_refuses_traversal_name(monkeypatch, tmp_path):
    _profiles_dir(monkeypatch, tmp_path)
    result = CliRunner().invoke(profiles, ["load", "--name", "../../etc/passwd"])
    assert result.exit_code != 0


def test_delete_refuses_traversal_name(monkeypatch, tmp_path):
    _profiles_dir(monkeypatch, tmp_path)
    victim = tmp_path / "home" / "victim.yaml"
    victim.write_text("k: v\n")
    result = CliRunner().invoke(profiles, ["delete", "--name", "../victim"])
    assert result.exit_code != 0
    assert victim.exists()


def test_dotfile_and_separator_names_refused(monkeypatch, tmp_path):
    _profiles_dir(monkeypatch, tmp_path)
    for bad in (".hidden", "a/b", "a\\b", "..", ""):
        result = CliRunner().invoke(profiles, ["save", "--name", bad])
        assert result.exit_code != 0, bad


def test_valid_name_still_saves(monkeypatch, tmp_path):
    prof_dir = _profiles_dir(monkeypatch, tmp_path)
    result = CliRunner().invoke(profiles, ["save", "--name", "prod-1"])
    assert result.exit_code == 0, result.output
    assert (prof_dir / "prod-1.yaml").exists()
