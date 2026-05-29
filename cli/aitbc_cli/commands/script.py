"""Script commands for AITBC CLI"""

import click
from ..utils import output, error, success
from pathlib import Path


@click.group()
def script():
    """Script execution and management"""
    pass


@script.command()
@click.option('--script-path', required=True, help='Path to script file')
@click.option('--args', help='Script arguments')
@click.pass_context
def run(ctx, script_path, args):
    """Run a script"""
    try:
        import subprocess
        cmd = [script_path]
        if args:
            cmd.extend(args.split())
        result = subprocess.run(cmd, capture_output=True, text=True)
        output({"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}, 
               ctx.obj.get('output_format', 'table'), title=f"Script: {script_path}")
    except Exception as e:
        error(f"Error running script: {e}")
        raise click.Abort()


@script.command()
@click.option('--script-dir', default='/opt/aitbc/scripts', help='Scripts directory')
@click.pass_context
def list(ctx, script_dir):
    """List available scripts"""
    try:
        scripts_path = Path(script_dir)
        if not scripts_path.exists():
            error(f"Scripts directory not found: {script_dir}")
            raise click.Abort()
        
        scripts = []
        for script_file in scripts_path.rglob('*.sh'):
            scripts.append({"name": script_file.name, "path": str(script_file)})
        
        output(scripts, ctx.obj.get('output_format', 'table'), title="Available Scripts")
    except Exception as e:
        error(f"Error listing scripts: {e}")
        raise click.Abort()
