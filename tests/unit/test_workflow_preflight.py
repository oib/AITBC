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


SCRIPT17 = Path(__file__).resolve().parents[2] / "scripts/workflow/17_security_hardening.sh"


def test_keystore_keeps_service_owner():
    """#959: keystore is never chowned to root."""
    src = SCRIPT17.read_text()
    assert "root:root /var/lib/aitbc/keystore" not in src


def test_sshd_config_validated_before_restart():
    src = SCRIPT17.read_text()
    assert "sshd -t" in src


def test_seds_are_idempotent():
    src = SCRIPT17.read_text()
    assert "^#?" in src or "grep -qE" in src


def test_summary_is_not_static():
    src = SCRIPT17.read_text()
    assert "Basic configuration completed" not in src
    assert "grep -E" in src or "stat -c" in src


def test_no_script_forges_block_fields():
    """#960: no workflow script rewrites proposer/genesis fields for importBlock."""
    wf = Path(__file__).resolve().parents[2] / "scripts" / "workflow"
    for sh in wf.glob("*.sh"):
        src = sh.read_text()
        assert "importBlock" not in src or "proposer" not in src, sh.name
    assert not (wf / "08_blockchain_sync_fix.sh").exists()


SCRIPT03 = Path(__file__).resolve().parents[2] / "scripts/workflow/03_follower_node_setup.sh"


def test_03_is_guarded_do_not_use():
    """#961: the broken follower setup is a stub that exits before doing harm."""
    src = SCRIPT03.read_text()
    head = src.split("exit 1")[0]
    assert "DO NOT USE" in head
    assert "setup.sh --open-island" in head


def test_no_single_quoted_rpc_vars_in_ssh():
    """#962: no ssh 'literal $VAR' call sites that only resolve on the caller."""
    import re

    bad = []
    for sh in Path(__file__).resolve().parents[2].joinpath("scripts/workflow").glob("*.sh"):
        for i, line in enumerate(sh.read_text().splitlines(), 1):
            m = re.search(r"ssh \S+ '[^']*\$(BLOCKCHAIN_RPC|RPC_URL|WALLET_ADDR|TOKEN|API_KEY)", line)
            if m:
                bad.append(f"{sh.name}:{i}")
    assert bad == []


def test_26_fails_on_empty_height():
    src = (Path(__file__).resolve().parents[2] / "scripts/workflow/26_production_deployment.sh").read_text()
    assert "height read failed" in src
