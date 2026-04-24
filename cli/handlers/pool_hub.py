"""Pool hub SLA and capacity management handlers."""

from aitbc.http_client import AITBCHTTPClient
from aitbc.exceptions import NetworkError


def handle_pool_hub_sla_metrics(args):
    """Get SLA metrics for a miner or all miners."""
    try:
        from commands.pool_hub import get_config as get_pool_hub_config
        config = get_pool_hub_config()
        
        if args.test_mode:
            print(" SLA Metrics (test mode):")
            print("  Uptime: 97.5%")
            print("  Response Time: 850ms")
            print("  Job Completion Rate: 92.3%")
            return
        
        pool_hub_url = getattr(config, "pool_hub_url", "http://localhost:8012")
        miner_id = getattr(args, "miner_id", None)
        
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=30)
        if miner_id:
            metrics = http_client.get(f"/sla/metrics/{miner_id}")
        else:
            metrics = http_client.get("/sla/metrics")
        
        print(" SLA Metrics:")
        for key, value in metrics.items():
            print(f"  {key}: {value}")
    except NetworkError as e:
        print(f"❌ Failed to get SLA metrics: {e}")
    except Exception as e:
        print(f"❌ Error getting SLA metrics: {e}")


def handle_pool_hub_sla_violations(args):
    """Get SLA violations across all miners."""
    try:
        from commands.pool_hub import get_config as get_pool_hub_config
        config = get_pool_hub_config()
        
        if args.test_mode:
            print("⚠️  SLA Violations (test mode):")
            print("  miner_001: response_time violation")
            return
        
        pool_hub_url = getattr(config, "pool_hub_url", "http://localhost:8012")
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=30)
        violations = http_client.get("/sla/violations")
        
        print("⚠️  SLA Violations:")
        for v in violations:
            print(f"  {v}")
    except NetworkError as e:
        print(f"❌ Failed to get violations: {e}")
    except Exception as e:
        print(f"❌ Error getting violations: {e}")


def handle_pool_hub_capacity_snapshots(args):
    """Get capacity planning snapshots."""
    try:
        from commands.pool_hub import get_config as get_pool_hub_config
        config = get_pool_hub_config()
        
        if args.test_mode:
            print("📊 Capacity Snapshots (test mode):")
            print("  Total Capacity: 1250 GPU")
            print("  Available: 320 GPU")
            return
        
        pool_hub_url = getattr(config, "pool_hub_url", "http://localhost:8012")
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=30)
        snapshots = http_client.get("/sla/capacity/snapshots")
        
        print("📊 Capacity Snapshots:")
        for s in snapshots:
            print(f"  {s}")
    except NetworkError as e:
        print(f"❌ Failed to get snapshots: {e}")
    except Exception as e:
        print(f"❌ Error getting snapshots: {e}")


def handle_pool_hub_capacity_forecast(args):
    """Get capacity forecast."""
    try:
        from commands.pool_hub import get_config as get_pool_hub_config
        config = get_pool_hub_config()
        
        if args.test_mode:
            print("🔮 Capacity Forecast (test mode):")
            print("  Projected Capacity: 1400 GPU")
            print("  Growth Rate: 12%")
            return
        
        pool_hub_url = getattr(config, "pool_hub_url", "http://localhost:8012")
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=30)
        forecast = http_client.get("/sla/capacity/forecast")
        
        print("🔮 Capacity Forecast:")
        for key, value in forecast.items():
            print(f"  {key}: {value}")
    except NetworkError as e:
        print(f"❌ Failed to get forecast: {e}")
    except Exception as e:
        print(f"❌ Error getting forecast: {e}")


def handle_pool_hub_capacity_recommendations(args):
    """Get scaling recommendations."""
    try:
        from commands.pool_hub import get_config as get_pool_hub_config
        config = get_pool_hub_config()
        
        if args.test_mode:
            print("💡 Capacity Recommendations (test mode):")
            print("  Type: scale_up")
            print("  Action: Add 50 GPU capacity")
            return
        
        pool_hub_url = getattr(config, "pool_hub_url", "http://localhost:8012")
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=30)
        recommendations = http_client.get("/sla/capacity/recommendations")
        
        print("💡 Capacity Recommendations:")
        for r in recommendations:
            print(f"  {r}")
    except NetworkError as e:
        print(f"❌ Failed to get recommendations: {e}")
    except Exception as e:
        print(f"❌ Error getting recommendations: {e}")


def handle_pool_hub_billing_usage(args):
    """Get billing usage data."""
    try:
        from commands.pool_hub import get_config as get_pool_hub_config
        config = get_pool_hub_config()
        
        if args.test_mode:
            print("💰 Billing Usage (test mode):")
            print("  Total GPU Hours: 45678")
            print("  Total Cost: $12500.50")
            return
        
        pool_hub_url = getattr(config, "pool_hub_url", "http://localhost:8012")
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=30)
        usage = http_client.get("/sla/billing/usage")
        
        print("💰 Billing Usage:")
        for key, value in usage.items():
            print(f"  {key}: {value}")
    except NetworkError as e:
        print(f"❌ Failed to get billing usage: {e}")
    except Exception as e:
        print(f"❌ Error getting billing usage: {e}")


def handle_pool_hub_billing_sync(args):
    """Trigger billing sync with coordinator-api."""
    try:
        from commands.pool_hub import get_config as get_pool_hub_config
        config = get_pool_hub_config()
        
        if args.test_mode:
            print("🔄 Billing sync triggered (test mode)")
            print("✅ Sync completed successfully")
            return
        
        pool_hub_url = getattr(config, "pool_hub_url", "http://localhost:8012")
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=60)
        result = http_client.post("/sla/billing/sync")
        
        print("🔄 Billing sync triggered")
        print(f"✅ {result.get('message', 'Success')}")
    except NetworkError as e:
        print(f"❌ Billing sync failed: {e}")
    except Exception as e:
        print(f"❌ Error triggering billing sync: {e}")


def handle_pool_hub_collect_metrics(args):
    """Trigger SLA metrics collection."""
    try:
        from commands.pool_hub import get_config as get_pool_hub_config
        config = get_pool_hub_config()
        
        if args.test_mode:
            print("📊 SLA metrics collection triggered (test mode)")
            print("✅ Collection completed successfully")
            return
        
        pool_hub_url = getattr(config, "pool_hub_url", "http://localhost:8012")
        http_client = AITBCHTTPClient(base_url=pool_hub_url, timeout=60)
        result = http_client.post("/sla/metrics/collect")
        
        print("📊 SLA metrics collection triggered")
        print(f"✅ {result.get('message', 'Success')}")
    except NetworkError as e:
        print(f"❌ Metrics collection failed: {e}")
    except Exception as e:
        print(f"❌ Error triggering metrics collection: {e}")
