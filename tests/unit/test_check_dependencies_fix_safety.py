"""UTILS-CHECK-DEPENDENCIES-FIX-KEYSTORE-OWNER-AND-UNPINNED-PIP-1 — --fix
must not hand the keystore to the installer user at 755 or run bare
unversioned pip installs."""

from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "scripts" / "utils" / "check-dependencies.sh").read_text()


def test_keystore_is_service_user_700_not_caller_755():
    assert 'chown aitbc:aitbc "$KEYSTORE_DIR"' in SCRIPT
    assert 'chmod 700 "$KEYSTORE_DIR"' in SCRIPT
    assert 'chown -R $USER:$USER "$KEYSTORE_DIR"' not in SCRIPT


def test_pip_install_is_pinned_or_refused():
    assert "pip install -r requirements.txt" in SCRIPT
    assert 'pip install "${missing_packages[@]}"' not in SCRIPT
