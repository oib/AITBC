"""Update the local AITBC installation from git and run the deploy script."""

import json
import subprocess
from pathlib import Path

import click

from ..utils import OUTPUT_FORMAT_OPTION, error, info, success
from ..utils.error_handling import abort
from ..utils.output import resolve_output_format

REPO_ROOT = Path(__file__).resolve().parents[3]
UPDATE_SCRIPT = REPO_ROOT / "scripts" / "deployment" / "update.sh"


def _short_sha(*rev: str, cwd: Path) -> str | None:
    """Return the short SHA for a revision, or None when it cannot be resolved."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", *rev],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _ahead_behind(cwd: Path, upstream: str) -> tuple[int, int] | None:
    """Return (ahead, behind) counts of HEAD vs upstream, or None."""
    result = subprocess.run(
        ["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream}"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        ahead, behind = (int(x) for x in result.stdout.split())
    except ValueError:
        return None
    return ahead, behind


def _report(before: str | None, after: str | None, remote: str, branch: str, deployed: bool, output_format: str):
    payload = {"before": before, "after": after, "remote": remote, "branch": branch, "deployed": deployed}
    if output_format == "json":
        click.echo(json.dumps(payload, indent=2))
        return
    info(f"Before: {before or 'unknown'}")
    info(f"After:  {after or 'unknown'}")
    info(f"Deployed: {'yes' if deployed else 'no'}")


def _check(repo: Path, remote: str, branch: str, upstream: str, before: str | None, output_format: str):
    """Fetch and report current vs remote SHA without changing the worktree."""
    if output_format != "json":
        info(f"Fetching {branch} from {remote}...")
    fetch = subprocess.run(
        ["git", "fetch", remote, branch],
        cwd=repo,
        check=False,
    )
    if fetch.returncode != 0:
        error(f"git fetch {remote} {branch} failed")
        raise click.Abort()
    remote_sha = _short_sha(upstream, cwd=repo) or _short_sha("FETCH_HEAD", cwd=repo)
    counts = _ahead_behind(repo, upstream)
    if output_format == "json":
        payload: dict[str, object] = {
            "before": before,
            "after": remote_sha,
            "remote": remote,
            "branch": branch,
            "deployed": False,
        }
        if counts:
            payload["ahead"], payload["behind"] = counts
        click.echo(json.dumps(payload, indent=2))
        return
    info(f"Local:  {before or 'unknown'}")
    info(f"Remote: {remote_sha or 'unknown'}")
    if counts:
        ahead, behind = counts
        if behind == 0 and ahead == 0:
            success("Up to date.")
        else:
            info(f"Ahead {ahead}, behind {behind}.")


@click.command(
    epilog="""Examples:

  aitbc update

  aitbc update --remote origin --branch main

  aitbc update --no-deploy

  aitbc update --check"""
)
@click.option("--remote", default="origin", help="Git remote to pull from (default: origin)")
@click.option("--branch", default="main", help="Branch to update to (default: main)")
@click.option("--no-deploy", is_flag=True, help="Fetch and fast-forward only; do not run update.sh")
@click.option("--check", is_flag=True, help="Fetch and report current vs remote SHA without changing anything")
@OUTPUT_FORMAT_OPTION
@click.pass_context
def update(ctx: click.Context, remote: str, branch: str, no_deploy: bool, check: bool, output_format: str | None):
    """Pull the latest code from git and run the deployment update script."""
    output_format = resolve_output_format(ctx, output_format)
    git_dir = REPO_ROOT / ".git"
    # .git is a file (not a dir) in linked worktrees — check existence, not dir-ness.
    if not git_dir.exists():
        abort(None, f"{REPO_ROOT} is not a git repository. Install or clone AITBC first.")

    upstream = f"{remote}/{branch}"
    before = _short_sha("HEAD", cwd=REPO_ROOT)

    if check:
        _check(REPO_ROOT, remote, branch, upstream, before, output_format)
        return

    if not no_deploy and not UPDATE_SCRIPT.exists():
        abort(None, f"Update script not found: {UPDATE_SCRIPT}")

    if output_format != "json":
        info(f"Pulling {branch} from {remote}...")
    pull = subprocess.run(
        ["git", "pull", "--ff-only", remote, branch],
        cwd=REPO_ROOT,
        check=False,
    )
    if pull.returncode != 0:
        error(f"git pull {remote} {branch} failed")
        raise click.Abort()

    _deploy(remote, branch, no_deploy, before, output_format)


def _deploy(remote: str, branch: str, no_deploy: bool, before: str | None, output_format: str):
    """Post-pull: report SHAs, optionally run update.sh."""
    after = _short_sha("HEAD", cwd=REPO_ROOT)

    if no_deploy:
        _report(before, after, remote, branch, deployed=False, output_format=output_format)
        if output_format != "json":
            success("Fast-forward complete (update.sh skipped via --no-deploy).")
        return

    if output_format != "json":
        info(f"Running {UPDATE_SCRIPT}...")
    run = subprocess.run(
        ["bash", str(UPDATE_SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
    )
    if run.returncode != 0:
        error(f"{UPDATE_SCRIPT} failed")
        raise click.Abort()

    _report(before, after, remote, branch, deployed=True, output_format=output_format)
    if output_format != "json":
        success("AITBC update completed.")
