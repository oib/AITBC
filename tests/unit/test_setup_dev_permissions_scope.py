"""UTILS-SETUP-DEV-PERMISSIONS-STRIPS-EXEC-AND-ROOT-SUDOERS-1 — the setup
script must not blanket-chmod the checkout or grant root-equivalent
sudoers wildcards."""

from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "scripts" / "utils" / "setup-dev-permissions.sh").read_text()


def test_no_blanket_file_chmod():
    assert "find $PROJECT_DIR -type f -exec chmod 664" not in SCRIPT


def test_secret_paths_are_pruned():
    for needle in (".env*", "venv", ".git", "keystore"):
        assert needle in SCRIPT, needle


def test_no_root_equivalent_sudoers():
    for needle in ("chown -R *", "chmod -R *", "git *", "make *", "pip3 install *", "kill -HUP *"):
        assert needle not in SCRIPT, needle


def test_sudoers_candidate_validated_before_install():
    assert "mktemp" in SCRIPT and "visudo -c" in SCRIPT and "install -m 0440" in SCRIPT
