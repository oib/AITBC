"""DEPLOY-ROLLBACK-BACKUP-BROKEN-1 — deploy backups live outside the repo.

deploy.sh kept BACKUP_DIR at ``$REPO_ROOT/.backup``, so the "backup" copied
the repository into a subdirectory of itself — and a failed copy only warned.
Worse, rollback looked for ``backup_*`` *files* (``-type f``) while backups
are directories, so a rollback could never find them. BACKUP_DIR now defaults
outside REPO_ROOT (overridable via AITBC_DEPLOY_BACKUP_DIR), a failed copy
aborts the deploy, and the rollback lookup uses ``-type d``.

The test runs the real setup_repository + rollback_deployment in a scratch
tree: backup, modify the tree, roll back, expect the pre-deploy content back.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO_ROOT / "scripts" / "deployment" / "deploy.sh"


def test_deploy_then_rollback_restores_the_previous_tree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()  # presence is all setup_repository checks
    (repo / "marker.txt").write_text("version-one\n")
    backup_dir = tmp_path / "backups"

    script = f"""
        source {DEPLOY_SH}
        REPO_ROOT={repo}
        BACKUP_DIR={backup_dir}
        check_root() {{ :; }}
        start_services() {{ :; }}

        setup_repository

        # a failed deploy changes the tree
        echo "version-two" > {repo}/marker.txt

        ROLLBACK_ASSUME_YES=yes rollback_deployment
    """
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (repo / "marker.txt").read_text() == "version-one\n"
    # the backup is a directory outside the repo that rollback can find
    assert not (repo / ".backup").exists()
    backups = [p for p in backup_dir.iterdir() if p.is_dir() and p.name.startswith("backup_")]
    assert len(backups) == 1


def test_backup_outside_repo_root_by_default():
    """The default must not be inside the tree it backs up (the self-copy bug)."""
    env = {**os.environ, "REPO_ROOT": "/x/aitbc"}
    env.pop("AITBC_DEPLOY_BACKUP_DIR", None)
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source {DEPLOY_SH}; case "$BACKUP_DIR" in "$REPO_ROOT"/*) exit 1;; esac',
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, "BACKUP_DIR default is still inside REPO_ROOT"
