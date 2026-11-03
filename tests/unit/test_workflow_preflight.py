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
    f = Path(__file__).resolve().parents[2] / "scripts/workflow/26_production_deployment.sh"
    if not f.exists():
        return  # retired under #965
    assert "height read failed" in f.read_text()


def test_no_script_scps_whole_env_between_hosts():
    """#963: no workflow script copies a whole node env to another host."""
    import re

    wf = Path(__file__).resolve().parents[2] / "scripts" / "workflow"
    for sh in wf.glob("*.sh"):
        for i, line in enumerate(sh.read_text().splitlines(), 1):
            if re.search(r"scp.*blockchain\.env\s+\S+:", line):
                raise AssertionError(f"{sh.name}:{i}: scp of whole env")
    assert not (wf / "11_network_optimizer.sh").exists()


def test_no_lowercase_env_seds_or_append_tuning():
    """#964: no workflow script seds lower-case keys or appends env/sysctl/fstab lines."""
    import re

    wf = Path(__file__).resolve().parents[2] / "scripts" / "workflow"
    for sh in wf.glob("*.sh"):
        src = sh.read_text()
        assert not re.search(r"sed -i 's/[a-z_]+=[0-9]+/", src), sh.name
        assert not re.search(r"echo '.*=' >> /etc/aitbc/blockchain\.env", src), sh.name
        assert ">> /etc/fstab" not in src, sh.name
    assert not (wf / "20_performance_tuning.sh").exists()


def test_production_deploy_scripts_retired():
    """#965: 26/42 report unchecked success — retired for setup.sh/update.sh."""
    wf = Path(__file__).resolve().parents[2] / "scripts" / "workflow"
    assert not (wf / "26_production_deployment.sh").exists()
    assert not (wf / "42_production_deployment_workflow.sh").exists()


def test_no_placeholder_sig_or_duplicate_send():
    """#966: no workflow script posts a placeholder signature or a send fallback."""
    wf = Path(__file__).resolve().parents[2] / "scripts" / "workflow"
    for sh in wf.glob("*.sh"):
        src = sh.read_text()
        assert "0x1234567890" not in src, sh.name
    assert not (wf / "09_transaction_manager.sh").exists()


def test_no_dead_rpc_routes_in_scenarios():
    """#967: /rpc/getBalance and /rpc/mineBlock are not served — no script may call them."""
    wf = Path(__file__).resolve().parents[2] / "scripts" / "workflow"
    for sh in wf.glob("*.sh"):
        src = sh.read_text()
        for dead in ("getBalance", "mineBlock"):
            assert dead not in src, f"{sh.name}: calls {dead}"


SCRIPT16 = Path(__file__).resolve().parents[2] / "scripts/workflow/16_monitoring_setup.sh"


def test_generated_health_check_reads_env():
    """#968: cron has no env — generated scripts source blockchain.env."""
    src = SCRIPT16.read_text()
    assert ". /etc/aitbc/blockchain.env" in src
    assert "mining/status" not in src


def test_cron_line_is_deduped():
    src = SCRIPT16.read_text()
    assert "grep -vF '/opt/aitbc/scripts/health_check.sh'" in src


SCRIPT36 = Path(__file__).resolve().parents[2] / "scripts/workflow/36_contract_security_testing.sh"


def test_findings_reach_the_verdict():
    """#969: the helper is exported for bash -c and findings gate the verdict."""
    src = SCRIPT36.read_text()
    assert "export -f log_security_finding" in src
    assert "FINDINGS_COUNT" in src
    assert "sendTx" not in src


SCRIPT37 = Path(__file__).resolve().parents[2] / "scripts/workflow/37_contract_event_monitoring.sh"
SCRIPT38 = Path(__file__).resolve().parents[2] / "scripts/workflow/38_contract_data_analytics.sh"


def test_37_helpers_exported_and_no_self_contradicting_test():
    src = SCRIPT37.read_text()
    assert "export -f log_contract_event log_service_event" in src
    assert "aitbc-events ]; then" not in src


def test_38_installs_no_cron_d_line():
    src = SCRIPT38.read_text()
    assert "cat > /etc/cron.d/aitbc-analytics" not in src


SCRIPT31 = Path(__file__).resolve().parents[2] / "scripts/workflow/31_consensus_testing.sh"


def test_partition_never_default():
    """#971: iptables DROP is behind --partition and a scratch-island check."""
    src = SCRIPT31.read_text()
    assert '"--partition"' in src
    assert "REFUSING partition test" in src
    assert "sendTx" not in src


SCRIPT06 = Path(__file__).resolve().parents[2] / "scripts/workflow/06_final_verification.sh"


def test_unreachable_peer_is_failure():
    """#972: no equal-height fallback when the peer cannot be reached."""
    src = SCRIPT06.read_text()
    assert "AITBC1_HEIGHT=$AITBC_HEIGHT" not in src
    assert "cannot verify sync" in src


SCRIPT22 = Path(__file__).resolve().parents[2] / "scripts/workflow/22_advanced_monitoring.sh"


def test_metrics_api_not_generated():
    """#973: the syntax-broken, unauthenticated Flask metrics file is gone."""
    src = SCRIPT22.read_text()
    assert "cat > /opt/aitbc/monitoring/metrics_api.py" not in src
    assert "flask_cors" not in src


SCRIPT25 = Path(__file__).resolve().parents[2] / "scripts/workflow/25_comprehensive_testing.sh"


def test_curls_fail_on_http_errors():
    """#975: every curl probe must use -f so a 404 body fails the test."""
    src = SCRIPT25.read_text()
    assert "curl -s " not in src
    assert "test -f /opt/aitbc" not in src and "test -f /etc/ssh" not in src
