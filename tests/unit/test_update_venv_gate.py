"""DEPLOY-SYNCVENV-STATUS-IGNORED-1 — a failed sync_venv must stop update.sh.

main() used to call ``sync_venv`` bare, so a broken/failed venv sync only
printed and the run went on to relink systemd units and restart every aitbc
service against a venv it had just failed to repair. The gate is the same
``|| exit 1`` the other gating steps (do_git_pull, relink_systemd,
run_migrations) already carry.

The test drives main() with every side-effecting step stubbed: sourcing
update.sh exposes its functions, so each step is replaced by a marker writer
and sync_venv is made to fail. The run must exit non-zero and must never
reach relink/restart. Nothing here touches systemd, /etc or a real venv.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "deployment" / "update.sh"


def _run_main_with_failing_sync_venv(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run ``main --no-pull --no-migrate --skip-backup`` with all steps stubbed.

    Every step after the pull writes a marker line when reached, and
    ``sync_venv`` returns 1. The fixed script exits before the markers are
    written; the broken one walks straight through to restart_services.
    """
    markers = tmp_path / "steps.log"
    deploy_log = tmp_path / "deploys.log"
    script = f"""
        source {UPDATE_SH}
        AITBC_DEPLOY_LOG={deploy_log}

        check_root() {{ :; }}
        check_repo() {{ :; }}
        run_pre_update_backup() {{ :; }}
        do_git_pull() {{ :; }}
        sync_venv() {{ echo "sync_venv" >> {markers}; return 1; }}
        relink_systemd() {{ echo "relink_systemd" >> {markers}; }}
        enable_services() {{ echo "enable_services" >> {markers}; }}
        ensure_env_files() {{ :; }}
        ensure_aitbc_wrapper() {{ :; }}
        ensure_monitor_log_files() {{ :; }}
        ensure_logrotate_config() {{ :; }}
        ensure_consensus_env_defaults() {{ :; }}
        ensure_gossip_defaults() {{ :; }}
        ensure_validator_secrets_scope() {{ :; }}
        render_website_files() {{ :; }}
        deploy_prometheus_rules() {{ :; }}
        run_migrations() {{ echo "run_migrations" >> {markers}; }}
        restart_services() {{ echo "restart_services" >> {markers}; }}
        run_health_check() {{ :; }}
        print_summary() {{ :; }}
        detect_gpu() {{ DETECTED_HARDWARE=nogpu; GPU_NAME=""; GPU_COUNT=0; }}

        main --no-pull --no-migrate --skip-backup
    """
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "AITBC_ROOT": str(tmp_path)},
    )


def test_failed_sync_venv_aborts_before_relink_and_restart(tmp_path):
    result = _run_main_with_failing_sync_venv(tmp_path)

    assert result.returncode != 0, "update.sh returned 0 with a failed venv sync\n" + result.stdout + result.stderr
    markers = tmp_path / "steps.log"
    reached = markers.read_text() if markers.exists() else ""
    assert "relink_systemd" not in reached
    assert "run_migrations" not in reached
    assert "restart_services" not in reached


def test_successful_sync_venv_still_runs_the_later_steps(tmp_path):
    """The gate must not turn into a refusal: a passing sync_venv proceeds."""
    result = _run_main_with_failing_sync_venv(tmp_path)
    # reuse the same harness but with sync_venv succeeding
    markers = tmp_path / "steps.log"
    markers.unlink(missing_ok=True)
    script = f"""
        source {UPDATE_SH}
        AITBC_DEPLOY_LOG={tmp_path / "deploys.log"}
        check_root() {{ :; }}
        check_repo() {{ :; }}
        run_pre_update_backup() {{ :; }}
        do_git_pull() {{ :; }}
        sync_venv() {{ echo "sync_venv" >> {markers}; return 0; }}
        relink_systemd() {{ echo "relink_systemd" >> {markers}; }}
        enable_services() {{ :; }}
        ensure_env_files() {{ :; }}
        ensure_aitbc_wrapper() {{ :; }}
        ensure_monitor_log_files() {{ :; }}
        ensure_logrotate_config() {{ :; }}
        ensure_consensus_env_defaults() {{ :; }}
        ensure_gossip_defaults() {{ :; }}
        ensure_validator_secrets_scope() {{ :; }}
        render_website_files() {{ :; }}
        deploy_prometheus_rules() {{ :; }}
        run_migrations() {{ :; }}
        restart_services() {{ echo "restart_services" >> {markers}; }}
        run_health_check() {{ :; }}
        print_summary() {{ :; }}
        detect_gpu() {{ DETECTED_HARDWARE=nogpu; GPU_NAME=""; GPU_COUNT=0; }}
        main --no-pull --no-migrate --skip-backup
    """
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    reached = markers.read_text()
    assert "sync_venv" in reached
    assert "relink_systemd" in reached
    assert "restart_services" in reached
