"""Bridge deposit-ledger read command (``aitbc bridge deposits``)."""

import json
import os
import subprocess
import sys

import click

from ._group import bridge
from ._helpers import _resolve_bridge_repo_root
from ...utils import output
from ...utils.error_handling import NotFoundError, abort


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
    stay in one place. Mutating admin commands use ``python -m
    bridge_monitor.admin`` on the hub with the bridge-monitor ``src``
    directory on PYTHONPATH; fleet operators may use the convenience wrapper
    in the companion aitbc-ops checkout instead.

    ``--output json``/``yaml`` emits the ledger rows as JSON/YAML; a
    ``--tx-hash`` with no matching row exits 2 (the same not-found code
    ``bridge status``/``bridge proof`` report).
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

    fmt = ctx.obj.get("output_format", "table") if ctx.obj else "table"
    as_json = fmt in ("json", "yaml")

    argv = [sys.executable, "-m", "bridge_monitor.admin"]
    if as_json:
        argv.append("--json")
    if tx_hash:
        argv += ["status", tx_hash]
    else:
        argv += ["list", "--limit", str(limit)]
        if status_filter:
            argv += ["--status", status_filter]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{monitor_src}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(monitor_src)
    proc = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30, check=False)
    if proc.returncode == 3 and tx_hash:
        # admin `status` exits 3 for an absent row — same not-found code
        # `bridge status`/`bridge proof` report (#2445).
        abort(ctx, f"no deposit row {tx_hash}", error_type=NotFoundError)
        return
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        abort(ctx, f"bridge ledger read failed ({proc.returncode}): {detail[-1] if detail else 'no output'}")
        return
    if as_json:
        try:
            output(json.loads(proc.stdout), fmt, title="Bridge Deposits")
        except ValueError:
            click.echo(proc.stdout, nl=False)
    elif proc.stdout:
        click.echo(proc.stdout, nl=False)
