#!/usr/bin/env python3
"""
Edge Node Deployment Script for AITBC Marketplace
Deploys edge node configuration and services
"""

import json
import os
import subprocess
import sys
from datetime import datetime

import click
import yaml


def load_config(config_file):
    """Load edge node configuration from YAML file"""
    with open(config_file) as f:
        return yaml.safe_load(f)

def deploy_redis_cache(config):
    """Deploy Redis cache layer"""
    click.echo(f"🔧 Deploying Redis cache for {config['edge_node_config']['node_id']}")

    # Check if Redis is running
    try:
        result = subprocess.run(['redis-cli', 'ping'], capture_output=True, text=True)
        if result.stdout.strip() == 'PONG':
            click.echo("✅ Redis is already running")
        else:
            click.echo("⚠️ Redis not responding, attempting to start...")
            # Start Redis if not running
            subprocess.run(['sudo', 'systemctl', 'start', 'redis-server'], check=True)
            click.echo("✅ Redis started")
    except FileNotFoundError:
        click.echo("❌ Redis not installed, installing...")
        subprocess.run(['sudo', 'apt-get', 'update'], check=True)
        subprocess.run(['sudo', 'apt-get', 'install', '-y', 'redis-server'], check=True)
        subprocess.run(['sudo', 'systemctl', 'start', 'redis-server'], check=True)
        click.echo("✅ Redis installed and started")

    # Configure Redis
    redis_config = config['edge_node_config']['caching']

    # Set Redis configuration
    redis_commands = [
        f"CONFIG SET maxmemory {redis_config['max_memory_mb']}mb",
        "CONFIG SET maxmemory-policy allkeys-lru",
        f"CONFIG SET timeout {redis_config['cache_ttl_seconds']}"
    ]

    for cmd in redis_commands:
        try:
            subprocess.run(['redis-cli', *cmd.split()], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            click.echo(f"⚠️ Could not set Redis config: {cmd}")

def deploy_monitoring(config):
    """Deploy monitoring agent"""
    click.echo(f"📊 Deploying monitoring for {config['edge_node_config']['node_id']}")

    monitoring_config = config['edge_node_config']['monitoring']

    # Create monitoring directory
    os.makedirs('/tmp/aitbc-monitoring', exist_ok=True)

    # Create monitoring script
    monitoring_script = f"""#!/bin/bash
# Monitoring script for {config['edge_node_config']['node_id']}
echo "{{{{'timestamp': '$(date -Iseconds)', 'node_id': '{config['edge_node_config']['node_id']}', 'status': 'monitoring'}}}}" > /tmp/aitbc-monitoring/status.json

# Check marketplace API health
curl -s http://localhost:{config['edge_node_config']['services'][0]['port']}/health/live > /dev/null
if [ $? -eq 0 ]; then
    echo "marketplace_healthy=true" >> /tmp/aitbc-monitoring/status.json
else
    echo "marketplace_healthy=false" >> /tmp/aitbc-monitoring/status.json
fi

# Check Redis health
redis-cli ping > /dev/null
if [ $? -eq 0 ]; then
    echo "redis_healthy=true" >> /tmp/aitbc-monitoring/status.json
else
    echo "redis_healthy=false" >> /tmp/aitbc-monitoring/status.json
fi
"""

    with open('/tmp/aitbc-monitoring/monitor.sh', 'w') as f:
        f.write(monitoring_script)

    os.chmod('/tmp/aitbc-monitoring/monitor.sh', 0o700)

    # Create systemd service for monitoring
    monitoring_service = f"""[Unit]
Description=AITBC Edge Node Monitoring - {config['edge_node_config']['node_id']}
After=network.target

[Service]
Type=simple
User=root
ExecStart=/tmp/aitbc-monitoring/monitor.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
"""

    service_file = f"/etc/systemd/system/aitbc-edge-monitoring-{config['edge_node_config']['node_id']}.service"

    with open(service_file, 'w') as f:
        f.write(monitoring_service)

    # Enable and start monitoring service
    subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
    subprocess.run(['sudo', 'systemctl', 'enable', f'aitbc-edge-monitoring-{config["edge_node_config"]["node_id"]}.service'], check=True)
    subprocess.run(['sudo', 'systemctl', 'start', f'aitbc-edge-monitoring-{config["edge_node_config"]["node_id"]}.service'], check=True)

    click.echo("✅ Monitoring agent deployed")

def optimize_network(config):
    """Apply network optimizations"""
    click.echo(f"🌐 Optimizing network for {config['edge_node_config']['node_id']}")

    network_config = config['edge_node_config']['network']

    # TCP optimizations
    tcp_params = {
        'net.core.rmem_max': '16777216',
        'net.core.wmem_max': '16777216',
        'net.ipv4.tcp_rmem': '4096 87380 16777216',
        'net.ipv4.tcp_wmem': '4096 65536 16777216',
        'net.ipv4.tcp_congestion_control': 'bbr',
        'net.core.netdev_max_backlog': '5000'
    }

    for param, value in tcp_params.items():
        try:
            subprocess.run(['sudo', 'sysctl', '-w', f'{param}={value}'], check=True, capture_output=True)
            click.echo(f"✅ Set {param}={value}")
        except subprocess.CalledProcessError:
            click.echo(f"⚠️ Could not set {param}")

def deploy_edge_services(config):
    """Deploy edge node services"""
    click.echo(f"🚀 Deploying edge services for {config['edge_node_config']['node_id']}")

    # Create edge service configuration
    edge_service_config = {
        'node_id': config['edge_node_config']['node_id'],
        'region': config['edge_node_config']['region'],
        'services': config['edge_node_config']['services'],
        'performance_targets': config['edge_node_config']['performance_targets'],
        'deployed_at': datetime.now().isoformat()
    }

    # Save configuration
    with open(f'/tmp/aitbc-edge-{config["edge_node_config"]["node_id"]}-config.json', 'w') as f:
        json.dump(edge_service_config, f, indent=2)

    click.echo("✅ Edge services configuration saved")

def validate_deployment(config):
    """Validate edge node deployment"""
    click.echo(f"✅ Validating deployment for {config['edge_node_config']['node_id']}")

    validation_results = {}

    # Check marketplace API
    try:
        response = subprocess.run(['curl', '-s', f'http://localhost:{config["edge_node_config"]["services"][0]["port"]}/health/live'],
                              capture_output=True, text=True, timeout=10)
        if response.status_code == 0:
            validation_results['marketplace_api'] = 'healthy'
        else:
            validation_results['marketplace_api'] = 'unhealthy'
    except Exception as e:
        validation_results['marketplace_api'] = f'error: {str(e)}'

    # Check Redis
    try:
        result = subprocess.run(['redis-cli', 'ping'], capture_output=True, text=True, timeout=5)
        if result.stdout.strip() == 'PONG':
            validation_results['redis'] = 'healthy'
        else:
            validation_results['redis'] = 'unhealthy'
    except Exception as e:
        validation_results['redis'] = f'error: {str(e)}'

    # Check monitoring
    try:
        result = subprocess.run(['systemctl', 'is-active', f'aitbc-edge-monitoring-{config["edge_node_config"]["node_id"]}.service'],
                              capture_output=True, text=True, timeout=5)
        validation_results['monitoring'] = result.stdout.strip()
    except Exception as e:
        validation_results['monitoring'] = f'error: {str(e)}'

    click.echo("📊 Validation Results:")
    for service, status in validation_results.items():
        click.echo(f"   {service}: {status}")

    return validation_results

def main():
    if len(sys.argv) != 2:
        click.echo("Usage: python deploy_edge_node.py <config_file>")
        sys.exit(1)

    config_file = sys.argv[1]

    if not os.path.exists(config_file):
        click.echo(f"❌ Configuration file {config_file} not found")
        sys.exit(1)

    try:
        config = load_config(config_file)

        click.echo(f"🚀 Deploying edge node: {config['edge_node_config']['node_id']}")
        click.echo(f"📍 Region: {config['edge_node_config']['region']}")
        click.echo(f"🌍 Location: {config['edge_node_config']['location']}")

        # Deploy components
        deploy_redis_cache(config)
        deploy_monitoring(config)
        optimize_network(config)
        deploy_edge_services(config)

        # Validate deployment
        validation_results = validate_deployment(config)

        # Save deployment status
        deployment_status = {
            'node_id': config['edge_node_config']['node_id'],
            'deployment_time': datetime.now().isoformat(),
            'validation_results': validation_results,
            'status': 'completed'
        }

        with open(f'/tmp/aitbc-edge-{config["edge_node_config"]["node_id"]}-deployment.json', 'w') as f:
            json.dump(deployment_status, f, indent=2)

        click.echo(f"✅ Edge node deployment completed for {config['edge_node_config']['node_id']}")

    except Exception as e:
        click.echo(f"❌ Deployment failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
