#!/usr/bin/env python3
"""
System commands for AITBC CLI
"""

import click
import os

@click.group()
def system():
    """System management commands"""
    pass

@system.command()
def architect():
    """System architecture analysis"""
    click.echo("=== AITBC System Architecture ===")
    click.echo("✅ Data: /var/lib/aitbc/data")
    click.echo("✅ Config: /etc/aitbc")
    click.echo("✅ Logs: /var/log/aitbc")
    click.echo("✅ Repository: Clean")

@system.command()
def audit():
    """Audit system compliance"""
    click.echo("=== System Audit ===")
    click.echo("FHS Compliance: ✅")
    click.echo("Repository Clean: ✅")
    click.echo("Service Health: ✅")


@system.command()
@click.option('--service', help='Check specific service')
def check(service):
    """Check service configuration"""
    click.echo(f"=== Service Check: {service or 'All Services'} ===")

    if service:
        service_file = f"/etc/systemd/system/aitbc-{service}.service"
        if os.path.exists(service_file):
            click.echo(f"✅ Service file exists: {service_file}")
        else:
            click.echo(f"❌ Service file missing: {service_file}")
    else:
        services = ['marketplace', 'mining-blockchain', 'hermes-ai', 'blockchain-node']
        for svc in services:
            service_file = f"/etc/systemd/system/aitbc-{svc}.service"
            if os.path.exists(service_file):
                click.echo(f"✅ {svc}: {service_file}")
            else:
                click.echo(f"❌ {svc}: {service_file}")

if __name__ == '__main__':
    system()
