"""Bridge deposit-ledger read command (``aitbc bridge deposits``)."""

import os
import subprocess
import sys

import click

from ._group import bridge
from ._helpers import _resolve_bridge_repo_root
from ...utils.error_handling import abort


@bridge.command(
    epilog="""Examples:

  aitbc bridge deposits

  aitbc bridge deposits --status funding --limit 10

  aitbc bridge deposits --tx-hash 0xabc...""",
)
@click.option("--status", "status_filter", default=None, help="Filter rows by deposit status (e.g. funding, failed)")
@click.option("--limit", default=50, type=int, help="Max ledger rows (default 50)")
@click.option("--tx-hash", "tx_hash", default=None, help="Show one deposit row by its eth tx hash")
@click.option(
    "--repo-root",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="AITBC checkout containing apps/bridge-monitor (default: inferred from cwd/interpreter or /opt/aitbc)",
)
@click.pass_context
def deposits(ctx, status_filter, limit, tx_hash, repo_root):
    """Read the bridge deposit ledger (ETH-side inbound deposits).

    The ledger is a sqlite database owned by aitbc-bridge-monitor on the hub;
    this runs the monitor's own read-only admin listing (`list`/`status`)
    rather than opening the file directly, so migrations and row decoding
    stay in one place. Mutating admin commands stay on
    ``scripts/ops/bridge-admin.sh``.
    """
    root = _resolve_bridge_repo_root(repo_root)
    monitor_src = root / "apps" / "bridge-monitor" / "src"
    if not (monitor_src / "bridge_monitor" / "admin.py").exists():
        abort(
            ctx,
            f"bridge-monitor sources not found under {root} — run this on the hub "
            "(the ledger lives there) or pass --repo-root / AITBC_REPO_ROOT",
        )
        return

    argv = [sys.executable, "-m", "bridge_monitor.admin"]
    if tx_hash:
        argv += ["status", tx_hash]
    else:
        argv += ["list", "--limit", str(limit)]
        if status_filter:
            argv += ["--status", status_filter]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{monitor_src}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(monitor_src)
    proc = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30, check=False)
    if proc.stdout:
        click.echo(proc.stdout, nl=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        abort(ctx, f"bridge ledger read failed ({proc.returncode}): {detail[-1] if detail else 'no output'}")
