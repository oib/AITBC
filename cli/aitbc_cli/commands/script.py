"""Script commands for AITBC CLI"""

from pathlib import Path

import click

from ..utils import output
from ..utils.error_handling import abort


@click.group()
def script():
    """Script execution and management"""
    pass


@script.command()
@click.option("--script-path", required=True, help="Path to script file")
@click.option("--args", help="Script arguments")
@click.pass_context
def run(ctx, script_path, args):
    """Run a script"""
    try:
        import subprocess

        cmd = [script_path]
        if args:
            cmd.extend(args.split())
        result = subprocess.run(cmd, capture_output=True, text=True)
        output(
            {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
            ctx.obj.get("output_format", "table"),
            title=f"Script: {script_path}",
        )
    except Exception as e:
        abort(ctx, f"Error running script: {e}", from_exception=e)


@script.command()
@click.option("--script-dir", default="/opt/aitbc/scripts", help="Scripts directory")
@click.pass_context
def list(ctx, script_dir):
    """List available scripts"""
    try:
        scripts_path = Path(script_dir)
        if not scripts_path.exists():
            abort(ctx, f"Scripts directory not found: {script_dir}")

        scripts = []
        for script_file in scripts_path.rglob("*.sh"):
            scripts.append({"name": script_file.name, "path": str(script_file)})

        output(scripts, ctx.obj.get("output_format", "table"), title="Available Scripts")
    except Exception as e:
        abort(ctx, f"Error listing scripts: {e}", from_exception=e)
