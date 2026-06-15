"""Blockchain event bridge handlers."""

import subprocess

from aitbc import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


def handle_bridge_health(args):
    """Health check for blockchain event bridge service."""
    try:
        from commands.legacy.blockchain_event_bridge import get_config as get_bridge_config

        config = get_bridge_config()

        if args.test_mode:
            logger.info("🏥 Blockchain Event Bridge Health (test mode):")
            logger.info("✅ Status: healthy")
            logger.info("📦 Service: blockchain-event-bridge")
            return

        bridge_url = getattr(config, "bridge_url", "http://localhost:8204")
        http_client = AITBCHTTPClient(base_url=bridge_url, timeout=10)
        health = http_client.get("/health")

        logger.info("🏥 Blockchain Event Bridge Health:")
        for key, value in health.items():
            logger.info("  %s: %s", key, value)
    except NetworkError as e:
        logger.error("❌ Health check failed: %s", e)
    except Exception as e:
        logger.error("❌ Error checking health: %s", e)


def handle_bridge_metrics(args):
    """Get Prometheus metrics from blockchain event bridge service."""
    try:
        from commands.legacy.blockchain_event_bridge import get_config as get_bridge_config

        config = get_bridge_config()

        if args.test_mode:
            logger.info("📊 Prometheus Metrics (test mode):")
            logger.info("  bridge_events_total: 103691")
            logger.info("  bridge_events_processed_total: 103691")
            return

        bridge_url = getattr(config, "bridge_url", "http://localhost:8204")
        http_client = AITBCHTTPClient(base_url=bridge_url, timeout=10)
        metrics = http_client.get("/metrics", return_response=True)

        logger.info("📊 Prometheus Metrics:")
        logger.info(metrics.text)
    except NetworkError as e:
        logger.error("❌ Failed to get metrics: %s", e)
    except Exception as e:
        logger.error("❌ Error getting metrics: %s", e)


def handle_bridge_status(args):
    """Get detailed status of blockchain event bridge service."""
    try:
        from commands.legacy.blockchain_event_bridge import get_config as get_bridge_config

        config = get_bridge_config()

        if args.test_mode:
            logger.info("📊 Blockchain Event Bridge Status (test mode):")
            logger.info("✅ Status: running")
            logger.info("🔔 Subscriptions: blocks, transactions, contract_events")
            return

        bridge_url = getattr(config, "bridge_url", "http://localhost:8204")
        http_client = AITBCHTTPClient(base_url=bridge_url, timeout=10)
        status = http_client.get("/")

        logger.info("📊 Blockchain Event Bridge Status:")
        for key, value in status.items():
            logger.info("  %s: %s", key, value)
    except NetworkError as e:
        logger.error("❌ Failed to get status: %s", e)
    except Exception as e:
        logger.error("❌ Error getting status: %s", e)


def handle_bridge_config(args):
    """Show current configuration of blockchain event bridge service."""
    try:
        from commands.legacy.blockchain_event_bridge import get_config as get_bridge_config

        config = get_bridge_config()

        if args.test_mode:
            logger.info("⚙️  Blockchain Event Bridge Configuration (test mode):")
            logger.info("🔗 Blockchain RPC URL: http://localhost:8006")
            logger.info("💬 Gossip Backend: redis")
            return

        bridge_url = getattr(config, "bridge_url", "http://localhost:8204")
        http_client = AITBCHTTPClient(base_url=bridge_url, timeout=10)
        service_config = http_client.get("/config")

        logger.info("⚙️  Blockchain Event Bridge Configuration:")
        for key, value in service_config.items():
            logger.info("  %s: %s", key, value)
    except NetworkError as e:
        logger.error("❌ Failed to get config: %s", e)
    except Exception as e:
        logger.error("❌ Error getting config: %s", e)


def handle_bridge_restart(args):
    """Restart blockchain event bridge service (via systemd)."""
    try:
        if args.test_mode:
            logger.info("🔄 Blockchain event bridge restart triggered (test mode)")
            logger.info("✅ Restart completed successfully")
            return

        result = subprocess.run(
            ["sudo", "systemctl", "restart", "aitbc-blockchain-event-bridge"], capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            logger.info("🔄 Blockchain event bridge restart triggered")
            logger.info("✅ Restart completed successfully")
        else:
            logger.error("❌ Restart failed: %s", result.stderr)
    except subprocess.TimeoutExpired:
        logger.info("❌ Restart timeout - service may be starting")
    except FileNotFoundError:
        logger.info("❌ systemctl not found - cannot restart service")
    except Exception as e:
        logger.error("❌ Error restarting service: %s", e)
