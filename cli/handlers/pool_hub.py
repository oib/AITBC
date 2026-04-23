"""Pool hub SLA and capacity management handlers."""

import requests


def handle_pool_hub_sla_metrics(args):
    """Get SLA metrics for a miner or all miners."""
    try:
        from commands.pool_hub import get_config as get_pool_hub_config
        config = get_pool_hub_config()
        
        if args.test_mode:
            print("📊 SLA Metrics (test mode):")
            print("⏱️  Uptime: 97.5%")
            print("⚡ Response Time: 850ms")
            print("✅ Job Completion Rate: 92.3%")
            return
        
        pool_hub_url = getattr(config, "pool_hub_url", "http://localhost:8012")
        miner_id = getattr(args, "miner_id", None)
        
        if miner_id:
            response = requests.get(f"{pool_hub_url}/sla/metrics/{miner_id}", timeout=30)
        else:
            response = requests.get(f"{pool_hub_url}/sla/metrics", timeout=30)
        
        if response.status_code == 200:
            metrics = response.json()
            print("📊 SLA Metrics:")
            for key, value in metrics.items():
                print(f"  {key}: {value}")
        else:
            print(f"❌ Failed to get SLA metrics: {response.text}")
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
        response = requests.get(f"{pool_hub_url}/sla/violations", timeout=30)
        
        if response.status_code == 200:
            violations = response.json()
            print("⚠️  SLA Violations:")
            for v in violations:
                print(f"  {v}")
        else:
            print(f"❌ Failed to get violations: {response.text}")
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
        response = requests.get(f"{pool_hub_url}/sla/capacity/snapshots", timeout=30)
        
        if response.status_code == 200:
            snapshots = response.json()
            print("📊 Capacity Snapshots:")
            for s in snapshots:
                print(f"  {s}")
        else:
            print(f"❌ Failed to get snapshots: {response.text}")
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
        response = requests.get(f"{pool_hub_url}/sla/capacity/forecast", timeout=30)
        
        if response.status_code == 200:
            forecast = response.json()
            print("🔮 Capacity Forecast:")
            for key, value in forecast.items():
                print(f"  {key}: {value}")
        else:
            print(f"❌ Failed to get forecast: {response.text}")
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
        response = requests.get(f"{pool_hub_url}/sla/capacity/recommendations", timeout=30)
        
        if response.status_code == 200:
            recommendations = response.json()
            print("💡 Capacity Recommendations:")
            for r in recommendations:
                print(f"  {r}")
        else:
            print(f"❌ Failed to get recommendations: {response.text}")
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
        response = requests.get(f"{pool_hub_url}/sla/billing/usage", timeout=30)
        
        if response.status_code == 200:
            usage = response.json()
            print("💰 Billing Usage:")
            for key, value in usage.items():
                print(f"  {key}: {value}")
        else:
            print(f"❌ Failed to get billing usage: {response.text}")
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
        response = requests.post(f"{pool_hub_url}/sla/billing/sync", timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            print("🔄 Billing sync triggered")
            print(f"✅ {result.get('message', 'Success')}")
        else:
            print(f"❌ Billing sync failed: {response.text}")
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
        response = requests.post(f"{pool_hub_url}/sla/metrics/collect", timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            print("📊 SLA metrics collection triggered")
            print(f"✅ {result.get('message', 'Success')}")
        else:
            print(f"❌ Metrics collection failed: {response.text}")
    except Exception as e:
        print(f"❌ Error triggering metrics collection: {e}")
