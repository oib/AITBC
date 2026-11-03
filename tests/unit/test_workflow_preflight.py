"""#956: the pre-flight script must never wipe a keystore unprompted or set a
fixed password."""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/workflow/01_preflight_setup.sh"


def test_no_fixed_keystore_password():
    assert "aitbc123" not in SCRIPT.read_text()


def test_password_is_random():
    src = SCRIPT.read_text()
    assert "/dev/urandom" in src or "openssl rand" in src


def test_wipe_requires_explicit_consent():
    """The destructive rm -rf block is only reached after an interactive
    confirm or --wipe — there is no path that skips the prompt when a setup
    exists."""
    src = SCRIPT.read_text()
    assert "--wipe" in src
    # the prompt is no longer gated on the service being active
    assert "systemctl is-active" not in src.split("rm -rf /var/lib/aitbc/keystore")[0]


def test_backup_runs_before_wipe():
    src = SCRIPT.read_text()
    backup = src.index("backup-preflight-")
    wipe = src.index("rm -rf /var/lib/aitbc/keystore")
    assert backup < wipe


def test_keystore_rm_is_inside_the_setup_flow():
    """The keystore delete only runs when ALREADY_SETUP was handled."""
    src = SCRIPT.read_text()
    assert "ALREADY_SETUP=true" in src
    assert 'if [ "$WIPE" != 1 ]' in src
