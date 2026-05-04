"""Blockchain event bridge handlers."""

import subprocess

from aitbc import AITBCHTTPClient, NetworkError


def handle_bridge_health(args):
    """Health check for blockchain event bridge service."""
    try:
        from commands.blockchain_event_bridge import get_config as get_bridge_config
        config = get_bridge_config()
        
        if args.test_mode:
            print("🏥 Blockchain Event Bridge Health (test mode):")
            print("✅ Status: healthy")
            print("📦 Service: blockchain-event-bridge")
            return
        
        bridge_url = getattr(config, "bridge_url", "http://localhost:8204")
        http_client = AITBCHTTPClient(base_url=bridge_url, timeout=10)
        health = http_client.get("/health")
        
        print("🏥 Blockchain Event Bridge Health:")
        for key, value in health.items():
            print(f"  {key}: {value}")
    except NetworkError as e:
        print(f"❌ Health check failed: {e}")
    except Exception as e:
        print(f"❌ Error checking health: {e}")


def handle_bridge_metrics(args):
    """Get Prometheus metrics from blockchain event bridge service."""
    try:
        from commands.blockchain_event_bridge import get_config as get_bridge_config
        config = get_bridge_config()
        
        if args.test_mode:
            print("📊 Prometheus Metrics (test mode):")
            print("  bridge_events_total: 103691")
            print("  bridge_events_processed_total: 103691")
            return
        
        bridge_url = getattr(config, "bridge_url", "http://localhost:8204")
        http_client = AITBCHTTPClient(base_url=bridge_url, timeout=10)
        metrics = http_client.get("/metrics", return_response=True)
        
        print("📊 Prometheus Metrics:")
        print(metrics.text)
    except NetworkError as e:
        print(f"❌ Failed to get metrics: {e}")
    except Exception as e:
        print(f"❌ Error getting metrics: {e}")


def handle_bridge_status(args):
    """Get detailed status of blockchain event bridge service."""
    try:
        from commands.blockchain_event_bridge import get_config as get_bridge_config
        config = get_bridge_config()
        
        if args.test_mode:
            print("📊 Blockchain Event Bridge Status (test mode):")
            print("✅ Status: running")
            print("🔔 Subscriptions: blocks, transactions, contract_events")
            return
        
        bridge_url = getattr(config, "bridge_url", "http://localhost:8204")
        http_client = AITBCHTTPClient(base_url=bridge_url, timeout=10)
        status = http_client.get("/")
        
        print("📊 Blockchain Event Bridge Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
    except NetworkError as e:
        print(f"❌ Failed to get status: {e}")
    except Exception as e:
        print(f"❌ Error getting status: {e}")


def handle_bridge_config(args):
    """Show current configuration of blockchain event bridge service."""
    try:
        from commands.blockchain_event_bridge import get_config as get_bridge_config
        config = get_bridge_config()
        
        if args.test_mode:
            print("⚙️  Blockchain Event Bridge Configuration (test mode):")
            print("🔗 Blockchain RPC URL: http://localhost:8006")
            print("💬 Gossip Backend: redis")
            return
        
        bridge_url = getattr(config, "bridge_url", "http://localhost:8204")
        http_client = AITBCHTTPClient(base_url=bridge_url, timeout=10)
        service_config = http_client.get("/config")
        
        print("⚙️  Blockchain Event Bridge Configuration:")
        for key, value in service_config.items():
            print(f"  {key}: {value}")
    except NetworkError as e:
        print(f"❌ Failed to get config: {e}")
    except Exception as e:
        print(f"❌ Error getting config: {e}")


def handle_bridge_restart(args):
    """Restart blockchain event bridge service (via systemd)."""
    try:
        if args.test_mode:
            print("🔄 Blockchain event bridge restart triggered (test mode)")
            print("✅ Restart completed successfully")
            return
        
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "aitbc-blockchain-event-bridge"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("🔄 Blockchain event bridge restart triggered")
            print("✅ Restart completed successfully")
        else:
            print(f"❌ Restart failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        print("❌ Restart timeout - service may be starting")
    except FileNotFoundError:
        print("❌ systemctl not found - cannot restart service")
    except Exception as e:
        print(f"❌ Error restarting service: {e}")
