"""Update the local AITBC installation from git and run the deploy script."""

import subprocess
from pathlib import Path

import click

from ..utils import error, info, success

REPO_ROOT = Path(__file__).resolve().parents[3]
UPDATE_SCRIPT = REPO_ROOT / "scripts" / "deployment" / "update.sh"


@click.command(
    epilog="""Examples:

  aitbc update

  aitbc update --remote origin --branch main"""
)
@click.option("--remote", default="origin", help="Git remote to pull from (default: origin)")
@click.option("--branch", default="main", help="Branch to update to (default: main)")
def update(remote: str, branch: str):
    """Pull the latest code from git and run the deployment update script."""
    git_dir = REPO_ROOT / ".git"
    if not git_dir.is_dir():
        error(f"{REPO_ROOT} is not a git repository. Install or clone AITBC first.")
        return

    if not UPDATE_SCRIPT.exists():
        error(f"Update script not found: {UPDATE_SCRIPT}")
        return

    info(f"Pulling {branch} from {remote}...")
    pull = subprocess.run(
        ["git", "pull", "--ff-only", remote, branch],
        cwd=REPO_ROOT,
        check=False,
    )
    if pull.returncode != 0:
        error(f"git pull {remote} {branch} failed")
        raise click.Abort()

    info(f"Running {UPDATE_SCRIPT}...")
    run = subprocess.run(
        ["bash", str(UPDATE_SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
    )
    if run.returncode != 0:
        error(f"{UPDATE_SCRIPT} failed")
        raise click.Abort()

    success("AITBC update completed.")
