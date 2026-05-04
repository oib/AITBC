"""
Blockchain Event Bridge CLI Commands for AITBC
Commands for managing blockchain event bridge service
"""

import click
import json
import requests
import subprocess
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional

@click.group()
def bridge():
    """Blockchain event bridge management commands"""
    pass

@bridge.command()
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def health(test_mode):
    """Health check for blockchain event bridge service"""
    try:
        if test_mode:
            # Mock data for testing
            mock_health = {
                "status": "healthy",
                "service": "blockchain-event-bridge",
                "version": "0.1.0",
                "uptime_seconds": 86400,
                "timestamp": datetime.now(datetime.UTC).isoformat()
            }
            
            click.echo("🏥 Blockchain Event Bridge Health:")
            click.echo("=" * 50)
            click.echo(f"✅ Status: {mock_health['status']}")
            click.echo(f"📦 Service: {mock_health['service']}")
            click.echo(f"📦 Version: {mock_health['version']}")
            click.echo(f"⏱️  Uptime: {mock_health['uptime_seconds']}s")
            click.echo(f"🕐 Timestamp: {mock_health['timestamp']}")
            return
        
        # Fetch from bridge service
        config = get_config()
        response = requests.get(
            f"{config.bridge_url}/health",
            timeout=10
        )
        
        if response.status_code == 200:
            health = response.json()
            
            click.echo("🏥 Blockchain Event Bridge Health:")
            click.echo("=" * 50)
            click.echo(f"✅ Status: {health.get('status', 'unknown')}")
            click.echo(f"📦 Service: {health.get('service', 'unknown')}")
            click.echo(f"📦 Version: {health.get('version', 'unknown')}")
            click.echo(f"⏱️  Uptime: {health.get('uptime_seconds', 0)}s")
            click.echo(f"🕐 Timestamp: {health.get('timestamp', 'unknown')}")
        else:
            click.echo(f"❌ Health check failed: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error checking health: {str(e)}", err=True)

@bridge.command()
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def metrics(test_mode):
    """Get Prometheus metrics from blockchain event bridge service"""
    try:
        if test_mode:
            # Mock data for testing
            mock_metrics = """
# HELP bridge_events_total Total number of blockchain events processed
# TYPE bridge_events_total counter
bridge_events_total{type="block"} 12345
bridge_events_total{type="transaction"} 67890
bridge_events_total{type="contract"} 23456
# HELP bridge_events_processed_total Total number of events successfully processed
# TYPE bridge_events_processed_total counter
bridge_events_processed_total 103691
# HELP bridge_events_failed_total Total number of events that failed processing
# TYPE bridge_events_failed_total counter
bridge_events_failed_total 123
# HELP bridge_processing_duration_seconds Event processing duration
# TYPE bridge_processing_duration_seconds histogram
bridge_processing_duration_seconds_bucket{le="0.1"} 50000
bridge_processing_duration_seconds_bucket{le="1.0"} 100000
bridge_processing_duration_seconds_sum 45000.5
bridge_processing_duration_seconds_count 103691
            """.strip()
            
            click.echo("📊 Prometheus Metrics:")
            click.echo("=" * 50)
            click.echo(mock_metrics)
            return
        
        # Fetch from bridge service
        config = get_config()
        response = requests.get(
            f"{config.bridge_url}/metrics",
            timeout=10
        )
        
        if response.status_code == 200:
            metrics = response.text
            click.echo("📊 Prometheus Metrics:")
            click.echo("=" * 50)
            click.echo(metrics)
        else:
            click.echo(f"❌ Failed to get metrics: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error getting metrics: {str(e)}", err=True)

@bridge.command()
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def status(test_mode):
    """Get detailed status of blockchain event bridge service"""
    try:
        if test_mode:
            # Mock data for testing
            mock_status = {
                "service": "blockchain-event-bridge",
                "status": "running",
                "version": "0.1.0",
                "subscriptions": {
                    "blocks": {
                        "enabled": True,
                        "topic": "blocks",
                        "last_block": 123456
                    },
                    "transactions": {
                        "enabled": True,
                        "topic": "transactions",
                        "last_transaction": "0xabc123..."
                    },
                    "contract_events": {
                        "enabled": True,
                        "contracts": [
                            "AgentStaking",
                            "PerformanceVerifier",
                            "AgentServiceMarketplace"
                        ],
                        "last_event": "0xdef456..."
                    }
                },
                "triggers": {
                    "agent_daemon": {
                        "enabled": True,
                        "events_triggered": 5432
                    },
                    "coordinator_api": {
                        "enabled": True,
                        "events_triggered": 8765
                    },
                    "marketplace": {
                        "enabled": True,
                        "events_triggered": 3210
                    }
                },
                "metrics": {
                    "events_processed": 103691,
                    "events_failed": 123,
                    "success_rate": 99.88
                }
            }
            
            click.echo("📊 Blockchain Event Bridge Status:")
            click.echo("=" * 50)
            click.echo(f"📦 Service: {mock_status['service']}")
            click.echo(f"✅ Status: {mock_status['status']}")
            click.echo(f"📦 Version: {mock_status['version']}")
            click.echo("")
            click.echo("🔔 Subscriptions:")
            for sub_type, sub_data in mock_status['subscriptions'].items():
                click.echo(f"   {sub_type}:")
                click.echo(f"      Enabled: {sub_data['enabled']}")
                if 'topic' in sub_data:
                    click.echo(f"      Topic: {sub_data['topic']}")
                if 'last_block' in sub_data:
                    click.echo(f"      Last Block: {sub_data['last_block']}")
                if 'contracts' in sub_data:
                    click.echo(f"      Contracts: {', '.join(sub_data['contracts'])}")
            click.echo("")
            click.echo("🎯 Triggers:")
            for trigger_type, trigger_data in mock_status['triggers'].items():
                click.echo(f"   {trigger_type}:")
                click.echo(f"      Enabled: {trigger_data['enabled']}")
                click.echo(f"      Events Triggered: {trigger_data['events_triggered']}")
            click.echo("")
            click.echo("📊 Metrics:")
            click.echo(f"   Events Processed: {mock_status['metrics']['events_processed']}")
            click.echo(f"   Events Failed: {mock_status['metrics']['events_failed']}")
            click.echo(f"   Success Rate: {mock_status['metrics']['success_rate']}%")
            
            return
        
        # Fetch from bridge service
        config = get_config()
        response = requests.get(
            f"{config.bridge_url}/",
            timeout=10
        )
        
        if response.status_code == 200:
            status = response.json()
            
            click.echo("📊 Blockchain Event Bridge Status:")
            click.echo("=" * 50)
            click.echo(f"📦 Service: {status.get('service', 'unknown')}")
            click.echo(f"✅ Status: {status.get('status', 'unknown')}")
            click.echo(f"📦 Version: {status.get('version', 'unknown')}")
            
            if 'subscriptions' in status:
                click.echo("")
                click.echo("🔔 Subscriptions:")
                for sub_type, sub_data in status['subscriptions'].items():
                    click.echo(f"   {sub_type}:")
                    click.echo(f"      Enabled: {sub_data.get('enabled', False)}")
        else:
            click.echo(f"❌ Failed to get status: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error getting status: {str(e)}", err=True)

@bridge.command()
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def config(test_mode):
    """Show current configuration of blockchain event bridge service"""
    try:
        if test_mode:
            # Mock data for testing
            mock_config = {
                "blockchain_rpc_url": "http://localhost:8006",
                "gossip_backend": "redis",
                "gossip_broadcast_url": "redis://localhost:6379",
                "coordinator_api_url": "http://localhost:8011",
                "coordinator_api_key": "***",
                "subscriptions": {
                    "blocks": True,
                    "transactions": True
                },
                "triggers": {
                    "agent_daemon": True,
                    "coordinator_api": True,
                    "marketplace": True
                },
                "polling": {
                    "enabled": False,
                    "interval_seconds": 60
                }
            }
            
            click.echo("⚙️  Blockchain Event Bridge Configuration:")
            click.echo("=" * 50)
            click.echo(f"🔗 Blockchain RPC URL: {mock_config['blockchain_rpc_url']}")
            click.echo(f"💬 Gossip Backend: {mock_config['gossip_backend']}")
            if mock_config.get('gossip_broadcast_url'):
                click.echo(f"📡 Gossip Broadcast URL: {mock_config['gossip_broadcast_url']}")
            click.echo(f"🎯 Coordinator API URL: {mock_config['coordinator_api_url']}")
            click.echo(f"🔑 Coordinator API Key: {mock_config['coordinator_api_key']}")
            click.echo("")
            click.echo("🔔 Subscriptions:")
            for sub, enabled in mock_config['subscriptions'].items():
                status = "✅" if enabled else "❌"
                click.echo(f"   {status} {sub}")
            click.echo("")
            click.echo("🎯 Triggers:")
            for trigger, enabled in mock_config['triggers'].items():
                status = "✅" if enabled else "❌"
                click.echo(f"   {status} {trigger}")
            click.echo("")
            click.echo("⏱️  Polling:")
            click.echo(f"   Enabled: {mock_config['polling']['enabled']}")
            click.echo(f"   Interval: {mock_config['polling']['interval_seconds']}s")
            
            return
        
        # Fetch from bridge service
        config = get_config()
        response = requests.get(
            f"{config.bridge_url}/config",
            timeout=10
        )
        
        if response.status_code == 200:
            service_config = response.json()
            
            click.echo("⚙️  Blockchain Event Bridge Configuration:")
            click.echo("=" * 50)
            click.echo(f"🔗 Blockchain RPC URL: {service_config.get('blockchain_rpc_url', 'unknown')}")
            click.echo(f"💬 Gossip Backend: {service_config.get('gossip_backend', 'unknown')}")
            if service_config.get('gossip_broadcast_url'):
                click.echo(f"📡 Gossip Broadcast URL: {service_config['gossip_broadcast_url']}")
            click.echo(f"🎯 Coordinator API URL: {service_config.get('coordinator_api_url', 'unknown')}")
        else:
            click.echo(f"❌ Failed to get config: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error getting config: {str(e)}", err=True)

@bridge.command()
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def restart(test_mode):
    """Restart blockchain event bridge service (via systemd)"""
    try:
        if test_mode:
            click.echo("🔄 Blockchain event bridge restart triggered (test mode)")
            click.echo("✅ Restart completed successfully")
            return
        
        # Restart via systemd
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "aitbc-blockchain-event-bridge"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                click.echo("🔄 Blockchain event bridge restart triggered")
                click.echo("✅ Restart completed successfully")
            else:
                click.echo(f"❌ Restart failed: {result.stderr}", err=True)
        except subprocess.TimeoutExpired:
            click.echo("❌ Restart timeout - service may be starting", err=True)
        except FileNotFoundError:
            click.echo("❌ systemctl not found - cannot restart service", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error restarting service: {str(e)}", err=True)

# Helper function to get config
def get_config():
    """Get CLI configuration"""
    try:
        from config import get_config
        return get_config()
    except ImportError:
        # Fallback for testing
        from types import SimpleNamespace
        return SimpleNamespace(
            bridge_url="http://localhost:8204",
            api_key="test-api-key"
        )

if __name__ == "__main__":
    bridge()
