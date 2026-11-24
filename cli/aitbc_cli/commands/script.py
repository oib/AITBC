"""Script commands for AITBC CLI"""

from pathlib import Path

import click

from ..utils import output
from ..utils.error_handling import abort


@click.group(
    epilog="""Examples:

  aitbc script list

  aitbc script run --script-path /opt/aitbc/scripts/setup.sh"""
)
def script():
    """Run scripts and list available scripts."""
    pass


@script.command(
    epilog="""Examples:

  aitbc script run --script-path /opt/aitbc/scripts/setup.sh

  aitbc script run --script-path /opt/aitbc/scripts/setup.sh --args '--verbose'"""
)
@click.option("--script-path", required=True, help="Path to script file under an allowed AITBC prefix")
@click.option("--args", help="Script arguments (shell-quoted, e.g. '--verbose \"a b\"')")
@click.option("--timeout", type=float, default=300, show_default=True, help="Kill the script after N seconds")
@click.pass_context
def run(ctx, script_path, args, timeout):
    """Run an allowlisted AITBC script with optional arguments."""
    import os
    import re
    import shlex
    import subprocess

    # Same prefix allowlist as ``aitbc system run-script`` — this command is
    # exposed through MCP, so an arbitrary --script-path is remote code
    # execution as the service user (#2886).
    from .system import _resolve_allowed_script_path

    try:
        resolved = _resolve_allowed_script_path(script_path)
    except click.ClickException as e:
        abort(ctx, str(e), from_exception=e)

    # The child must not inherit credential-bearing env vars (API keys,
    # tokens, wallet secrets) — a script only needs the operational env.
    secret_env = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|MNEMONIC|SEED|PRIVATE)", re.IGNORECASE)
    child_env = {k: v for k, v in os.environ.items() if not secret_env.search(k)}

    try:
        cmd = [str(resolved)]
        if args:
            cmd.extend(shlex.split(args))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=child_env)
        output(
            {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
            ctx.obj.get("output_format", "table"),
            title=f"Script: {script_path}",
        )
        if result.returncode != 0:
            # SystemExit (not ctx.exit): click's Exit is a RuntimeError and
            # would be re-caught by the handler below.
            raise SystemExit(result.returncode if 0 < result.returncode < 256 else 1)
    except subprocess.TimeoutExpired:
        abort(ctx, f"Script timed out after {timeout}s: {script_path}")
    except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as e:
        abort(ctx, f"Error running script: {e}", from_exception=e)


@script.command(
    epilog="""Examples:

  aitbc script list

  aitbc script list --script-dir /opt/aitbc/scripts"""
)
@click.option("--script-dir", default="/opt/aitbc/scripts", help="Scripts directory")
@click.pass_context
def list(ctx, script_dir):
    """List available scripts in the script directory."""
    try:
        scripts_path = Path(script_dir)
        if not scripts_path.exists():
            abort(ctx, f"Scripts directory not found: {script_dir}")

        scripts = []
        for script_file in scripts_path.rglob("*.sh"):
            scripts.append({"name": script_file.name, "path": str(script_file)})

        output(scripts, ctx.obj.get("output_format", "table"), title="Available Scripts")
    except (OSError, ValueError, TypeError, AttributeError, RuntimeError) as e:
        abort(ctx, f"Error listing scripts: {e}", from_exception=e)
