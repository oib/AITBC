"""Authentication commands for AITBC CLI"""

import click
import os
from typing import Optional
from ..auth import AuthManager
from ..utils import output, success, error, warning


@click.group()
def auth():
    """Manage API keys and authentication"""
    pass


@auth.command()
@click.argument("api_key")
@click.option("--environment", default="default", help="Environment name (default, dev, staging, prod)")
@click.pass_context
def login(ctx, api_key: str, environment: str):
    """Store API key for authentication"""
    auth_manager = AuthManager()
    
    # Validate API key format (basic check)
    if not api_key or len(api_key) < 10:
        error("Invalid API key format")
        ctx.exit(1)
        return
    
    auth_manager.store_credential("client", api_key, environment)
    
    output({
        "status": "logged_in",
        "environment": environment,
        "note": "API key stored securely"
    }, ctx.obj['output_format'])


@auth.command()
@click.option("--environment", default="default", help="Environment name")
@click.pass_context
def logout(ctx, environment: str):
    """Remove stored API key"""
    auth_manager = AuthManager()
    
    auth_manager.delete_credential("client", environment)
    
    output({
        "status": "logged_out",
        "environment": environment
    }, ctx.obj['output_format'])


@auth.command()
@click.option("--environment", default="default", help="Environment name")
@click.option("--show", is_flag=True, help="Show the actual API key")
@click.pass_context
def token(ctx, environment: str, show: bool):
    """Show stored API key"""
    auth_manager = AuthManager()
    
    api_key = auth_manager.get_credential("client", environment)
    
    if api_key:
        if show:
            output({
                "api_key": api_key,
                "environment": environment
            }, ctx.obj['output_format'])
        else:
            output({
                "api_key": "***REDACTED***",
                "environment": environment,
                "length": len(api_key)
            }, ctx.obj['output_format'])
    else:
        output({
            "message": "No API key stored",
            "environment": environment
        }, ctx.obj['output_format'])


@auth.command()
@click.pass_context
def status(ctx):
    """Show authentication status"""
    auth_manager = AuthManager()
    
    credentials = auth_manager.list_credentials()
    
    if credentials:
        output({
            "status": "authenticated",
            "stored_credentials": credentials
        }, ctx.obj['output_format'])
    else:
        output({
            "status": "not_authenticated",
            "message": "No stored credentials found"
        }, ctx.obj['output_format'])


@auth.command()
@click.option("--environment", default="default", help="Environment name")
@click.pass_context
def refresh(ctx, environment: str):
    """Refresh authentication (placeholder for token refresh)"""
    auth_manager = AuthManager()
    
    api_key = auth_manager.get_credential("client", environment)
    
    if api_key:
        # In a real implementation, this would refresh the token
        output({
            "status": "refreshed",
            "environment": environment,
            "message": "Authentication refreshed (placeholder)"
        }, ctx.obj['output_format'])
    else:
        error(f"No API key found for environment: {environment}")
        ctx.exit(1)


@auth.group()
def keys():
    """Manage multiple API keys"""
    pass


@keys.command()
@click.pass_context
def list(ctx):
    """List all stored API keys"""
    auth_manager = AuthManager()
    credentials = auth_manager.list_credentials()
    
    if credentials:
        output({
            "credentials": credentials
        }, ctx.obj['output_format'])
    else:
        output({
            "message": "No credentials stored"
        }, ctx.obj['output_format'])


@keys.command()
@click.argument("name")
@click.argument("api_key")
@click.option("--permissions", help="Comma-separated permissions (client,miner,admin)")
@click.option("--environment", default="default", help="Environment name")
@click.pass_context
def create(ctx, name: str, api_key: str, permissions: Optional[str], environment: str):
    """Create a new API key entry"""
    auth_manager = AuthManager()
    
    if not api_key or len(api_key) < 10:
        error("Invalid API key format")
        return
    
    auth_manager.store_credential(name, api_key, environment)
    
    output({
        "status": "created",
        "name": name,
        "environment": environment,
        "permissions": permissions or "none"
    }, ctx.obj['output_format'])


@keys.command()
@click.argument("name")
@click.option("--environment", default="default", help="Environment name")
@click.pass_context
def revoke(ctx, name: str, environment: str):
    """Revoke an API key"""
    auth_manager = AuthManager()
    
    auth_manager.delete_credential(name, environment)
    
    output({
        "status": "revoked",
        "name": name,
        "environment": environment
    }, ctx.obj['output_format'])


@keys.command()
@click.pass_context
def rotate(ctx):
    """Rotate all API keys (placeholder)"""
    warning("Key rotation not implemented yet")
    
    output({
        "message": "Key rotation would update all stored keys",
        "status": "placeholder"
    }, ctx.obj['output_format'])


@auth.command()
@click.argument("name")
@click.pass_context
def import_env(ctx, name: str):
    """Import API key from environment variable"""
    env_var = f"{name.upper()}_API_KEY"
    api_key = os.getenv(env_var)
    
    if not api_key:
        error(f"Environment variable {env_var} not set")
        ctx.exit(1)
        return
    
    auth_manager = AuthManager()
    auth_manager.store_credential(name, api_key)
    
    output({
        "status": "imported",
        "name": name,
        "source": env_var
    }, ctx.obj['output_format'])
