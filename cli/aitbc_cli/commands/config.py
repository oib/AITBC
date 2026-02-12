"""Configuration commands for AITBC CLI"""

import click
import os
import yaml
import json
from pathlib import Path
from typing import Optional, Dict, Any
from ..config import get_config, Config
from ..utils import output, error, success


@click.group()
def config():
    """Manage CLI configuration"""
    pass


@config.command()
@click.pass_context
def show(ctx):
    """Show current configuration"""
    config = ctx.obj['config']
    
    config_dict = {
        "coordinator_url": config.coordinator_url,
        "api_key": "***REDACTED***" if config.api_key else None,
        "timeout": getattr(config, 'timeout', 30),
        "config_file": getattr(config, 'config_file', None)
    }
    
    output(config_dict, ctx.obj['output_format'])


@config.command()
@click.argument("key")
@click.argument("value")
@click.option("--global", "global_config", is_flag=True, help="Set global config")
@click.pass_context
def set(ctx, key: str, value: str, global_config: bool):
    """Set configuration value"""
    config = ctx.obj['config']
    
    # Determine config file path
    if global_config:
        config_dir = Path.home() / ".config" / "aitbc"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"
    else:
        config_file = Path.cwd() / ".aitbc.yaml"
    
    # Load existing config
    if config_file.exists():
        with open(config_file) as f:
            config_data = yaml.safe_load(f) or {}
    else:
        config_data = {}
    
    # Set the value
    if key == "api_key":
        config_data["api_key"] = value
        if ctx.obj['output_format'] == 'table':
            success("API key set (use --global to set permanently)")
    elif key == "coordinator_url":
        config_data["coordinator_url"] = value
        if ctx.obj['output_format'] == 'table':
            success(f"Coordinator URL set to: {value}")
    elif key == "timeout":
        try:
            config_data["timeout"] = int(value)
            if ctx.obj['output_format'] == 'table':
                success(f"Timeout set to: {value}s")
        except ValueError:
            error("Timeout must be an integer")
            ctx.exit(1)
    else:
        error(f"Unknown configuration key: {key}")
        ctx.exit(1)
    
    # Save config
    with open(config_file, 'w') as f:
        yaml.dump(config_data, f, default_flow_style=False)
    
    output({
        "config_file": str(config_file),
        "key": key,
        "value": value
    }, ctx.obj['output_format'])


@config.command()
@click.option("--global", "global_config", is_flag=True, help="Show global config")
def path(global_config: bool):
    """Show configuration file path"""
    if global_config:
        config_dir = Path.home() / ".config" / "aitbc"
        config_file = config_dir / "config.yaml"
    else:
        config_file = Path.cwd() / ".aitbc.yaml"
    
    output({
        "config_file": str(config_file),
        "exists": config_file.exists()
    })


@config.command()
@click.option("--global", "global_config", is_flag=True, help="Edit global config")
@click.pass_context
def edit(ctx, global_config: bool):
    """Open configuration file in editor"""
    # Determine config file path
    if global_config:
        config_dir = Path.home() / ".config" / "aitbc"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"
    else:
        config_file = Path.cwd() / ".aitbc.yaml"
    
    # Create if doesn't exist
    if not config_file.exists():
        config = ctx.obj['config']
        config_data = {
            "coordinator_url": config.coordinator_url,
            "timeout": getattr(config, 'timeout', 30)
        }
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)
    
    # Open in editor
    editor = os.getenv('EDITOR', 'nano')
    os.system(f"{editor} {config_file}")


@config.command()
@click.option("--global", "global_config", is_flag=True, help="Reset global config")
@click.pass_context
def reset(ctx, global_config: bool):
    """Reset configuration to defaults"""
    # Determine config file path
    if global_config:
        config_dir = Path.home() / ".config" / "aitbc"
        config_file = config_dir / "config.yaml"
    else:
        config_file = Path.cwd() / ".aitbc.yaml"
    
    if not config_file.exists():
        output({"message": "No configuration file found"})
        return
    
    if not click.confirm(f"Reset configuration at {config_file}?"):
        return
    
    # Remove config file
    config_file.unlink()
    success("Configuration reset to defaults")


@config.command()
@click.option("--format", "output_format", type=click.Choice(['yaml', 'json']), default='yaml', help="Output format")
@click.option("--global", "global_config", is_flag=True, help="Export global config")
@click.pass_context
def export(ctx, output_format: str, global_config: bool):
    """Export configuration"""
    # Determine config file path
    if global_config:
        config_dir = Path.home() / ".config" / "aitbc"
        config_file = config_dir / "config.yaml"
    else:
        config_file = Path.cwd() / ".aitbc.yaml"
    
    if not config_file.exists():
        error("No configuration file found")
        ctx.exit(1)
    
    with open(config_file) as f:
        config_data = yaml.safe_load(f)
    
    # Redact sensitive data
    if 'api_key' in config_data:
        config_data['api_key'] = "***REDACTED***"
    
    if output_format == 'json':
        click.echo(json.dumps(config_data, indent=2))
    else:
        click.echo(yaml.dump(config_data, default_flow_style=False))


@config.command()
@click.argument("file_path")
@click.option("--merge", is_flag=True, help="Merge with existing config")
@click.option("--global", "global_config", is_flag=True, help="Import to global config")
@click.pass_context
def import_config(ctx, file_path: str, merge: bool, global_config: bool):
    """Import configuration from file"""
    import_file = Path(file_path)
    
    if not import_file.exists():
        error(f"File not found: {file_path}")
        ctx.exit(1)
    
    # Load import file
    try:
        with open(import_file) as f:
            if import_file.suffix.lower() == '.json':
                import_data = json.load(f)
            else:
                import_data = yaml.safe_load(f)
    except json.JSONDecodeError:
        error("Invalid JSON data")
        ctx.exit(1)
    except Exception as e:
        error(f"Failed to parse file: {e}")
        ctx.exit(1)
    
    # Determine target config file
    if global_config:
        config_dir = Path.home() / ".config" / "aitbc"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.yaml"
    else:
        config_file = Path.cwd() / ".aitbc.yaml"
    
    # Load existing config if merging
    if merge and config_file.exists():
        with open(config_file) as f:
            config_data = yaml.safe_load(f) or {}
        config_data.update(import_data)
    else:
        config_data = import_data
    
    # Save config
    with open(config_file, 'w') as f:
        yaml.dump(config_data, f, default_flow_style=False)
    
    if ctx.obj['output_format'] == 'table':
        success(f"Configuration imported to {config_file}")


@config.command()
@click.pass_context
def validate(ctx):
    """Validate configuration"""
    config = ctx.obj['config']
    
    errors = []
    warnings = []
    
    # Validate coordinator URL
    if not config.coordinator_url:
        errors.append("Coordinator URL is not set")
    elif not config.coordinator_url.startswith(('http://', 'https://')):
        errors.append("Coordinator URL must start with http:// or https://")
    
    # Validate API key
    if not config.api_key:
        warnings.append("API key is not set")
    elif len(config.api_key) < 10:
        errors.append("API key appears to be too short")
    
    # Validate timeout
    timeout = getattr(config, 'timeout', 30)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        errors.append("Timeout must be a positive number")
    
    # Output results
    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }
    
    if errors:
        error("Configuration validation failed")
        ctx.exit(1)
    elif warnings:
        if ctx.obj['output_format'] == 'table':
            success("Configuration valid with warnings")
    else:
        if ctx.obj['output_format'] == 'table':
            success("Configuration is valid")
    
    output(result, ctx.obj['output_format'])


@config.command()
def environments():
    """List available environments"""
    env_vars = [
        'AITBC_COORDINATOR_URL',
        'AITBC_API_KEY',
        'AITBC_TIMEOUT',
        'AITBC_CONFIG_FILE',
        'CLIENT_API_KEY',
        'MINER_API_KEY',
        'ADMIN_API_KEY'
    ]
    
    env_data = {}
    for var in env_vars:
        value = os.getenv(var)
        if value:
            if 'API_KEY' in var:
                value = "***REDACTED***"
            env_data[var] = value
    
    output({
        "environment_variables": env_data,
        "note": "Use export VAR=value to set environment variables"
    })


@config.group()
def profiles():
    """Manage configuration profiles"""
    pass


@profiles.command()
@click.argument("name")
@click.pass_context
def save(ctx, name: str):
    """Save current configuration as a profile"""
    config = ctx.obj['config']
    
    # Create profiles directory
    profiles_dir = Path.home() / ".config" / "aitbc" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    
    profile_file = profiles_dir / f"{name}.yaml"
    
    # Save profile (without API key)
    profile_data = {
        "coordinator_url": config.coordinator_url,
        "timeout": getattr(config, 'timeout', 30)
    }
    
    with open(profile_file, 'w') as f:
        yaml.dump(profile_data, f, default_flow_style=False)
    
    if ctx.obj['output_format'] == 'table':
        success(f"Profile '{name}' saved")


@profiles.command()
def list():
    """List available profiles"""
    profiles_dir = Path.home() / ".config" / "aitbc" / "profiles"
    
    if not profiles_dir.exists():
        output({"profiles": []})
        return
    
    profiles = []
    for profile_file in profiles_dir.glob("*.yaml"):
        with open(profile_file) as f:
            profile_data = yaml.safe_load(f)
        
        profiles.append({
            "name": profile_file.stem,
            "coordinator_url": profile_data.get("coordinator_url"),
            "timeout": profile_data.get("timeout", 30)
        })
    
    output({"profiles": profiles})


@profiles.command()
@click.argument("name")
@click.pass_context
def load(ctx, name: str):
    """Load a configuration profile"""
    profiles_dir = Path.home() / ".config" / "aitbc" / "profiles"
    profile_file = profiles_dir / f"{name}.yaml"
    
    if not profile_file.exists():
        error(f"Profile '{name}' not found")
        ctx.exit(1)
    
    with open(profile_file) as f:
        profile_data = yaml.safe_load(f)
    
    # Load to current config
    config_file = Path.cwd() / ".aitbc.yaml"
    
    with open(config_file, 'w') as f:
        yaml.dump(profile_data, f, default_flow_style=False)
    
    if ctx.obj['output_format'] == 'table':
        success(f"Profile '{name}' loaded")


@profiles.command()
@click.argument("name")
@click.pass_context
def delete(ctx, name: str):
    """Delete a configuration profile"""
    profiles_dir = Path.home() / ".config" / "aitbc" / "profiles"
    profile_file = profiles_dir / f"{name}.yaml"
    
    if not profile_file.exists():
        error(f"Profile '{name}' not found")
        ctx.exit(1)
    
    if not click.confirm(f"Delete profile '{name}'?"):
        return
    
    profile_file.unlink()
    if ctx.obj['output_format'] == 'table':
        success(f"Profile '{name}' deleted")


@config.command(name="set-secret")
@click.argument("key")
@click.argument("value")
@click.pass_context
def set_secret(ctx, key: str, value: str):
    """Set an encrypted configuration value"""
    from ..utils import encrypt_value
    
    config_dir = Path.home() / ".config" / "aitbc"
    config_dir.mkdir(parents=True, exist_ok=True)
    secrets_file = config_dir / "secrets.json"
    
    secrets = {}
    if secrets_file.exists():
        with open(secrets_file) as f:
            secrets = json.load(f)
    
    secrets[key] = encrypt_value(value)
    
    with open(secrets_file, "w") as f:
        json.dump(secrets, f, indent=2)
    
    # Restrict file permissions
    secrets_file.chmod(0o600)
    
    if ctx.obj['output_format'] == 'table':
        success(f"Secret '{key}' saved (encrypted)")
    output({"key": key, "status": "encrypted"}, ctx.obj['output_format'])


@config.command(name="get-secret")
@click.argument("key")
@click.pass_context
def get_secret(ctx, key: str):
    """Get a decrypted configuration value"""
    from ..utils import decrypt_value
    
    secrets_file = Path.home() / ".config" / "aitbc" / "secrets.json"
    
    if not secrets_file.exists():
        error("No secrets file found")
        ctx.exit(1)
        return
    
    with open(secrets_file) as f:
        secrets = json.load(f)
    
    if key not in secrets:
        error(f"Secret '{key}' not found")
        ctx.exit(1)
        return
    
    decrypted = decrypt_value(secrets[key])
    output({"key": key, "value": decrypted}, ctx.obj['output_format'])


# Add profiles group to config
config.add_command(profiles)
