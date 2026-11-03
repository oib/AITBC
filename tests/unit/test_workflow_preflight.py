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


SCRIPT13 = Path(__file__).resolve().parents[2] / "scripts/workflow/13_maintenance_automation.sh"


def test_maintenance_never_commits_or_pushes():
    """#957: git add/commit/push are gone from the script entirely."""
    src = SCRIPT13.read_text()
    code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    for bad in ("git add", "git commit", "git push"):
        assert bad not in code


def test_restart_is_conditional_on_real_change():
    src = SCRIPT13.read_text()
    assert "_before=$(git rev-parse HEAD)" in src
    assert '!= "$_before"' in src


SCRIPT27 = Path(__file__).resolve().parents[2] / "scripts/workflow/27_operations_automation.sh"
SCRIPT21 = Path(__file__).resolve().parents[2] / "scripts/workflow/21_maintenance_automation.sh"


def test_no_blanket_tmp_delete():
    """#958: no unfiltered find -delete over /tmp or /var/tmp."""
    src = SCRIPT27.read_text()
    assert "find /tmp -mtime" not in src
    assert "find /var/tmp -mtime" not in src
    # the dedicated dir + name filter is required
    assert "-name 'aitbc-*' -delete" in src


def test_vacuum_failures_are_visible():
    """#958: no || true on VACUUM — a failed vacuum must error."""
    for s in (SCRIPT21, SCRIPT27):
        src = s.read_text()
        for line in src.splitlines():
            if "VACUUM" in line:
                assert "|| true" not in line, f"{s.name}: {line.strip()}"
