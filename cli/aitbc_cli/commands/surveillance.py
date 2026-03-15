#!/usr/bin/env python3
"""
Trading Surveillance CLI Commands
Monitor and detect market manipulation and suspicious trading activities
"""

import click
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from aitbc_cli.imports import ensure_coordinator_api_imports

ensure_coordinator_api_imports()

try:
    from app.services.trading_surveillance import (
        start_surveillance, stop_surveillance, get_alerts,
        get_surveillance_summary, AlertLevel
    )
    _import_error = None
except ImportError as e:
    _import_error = e

    def _missing(*args, **kwargs):
        raise ImportError(
            f"Required service module 'app.services.trading_surveillance' could not be imported: {_import_error}. "
            "Ensure coordinator-api dependencies are installed and the source directory is accessible."
        )
    start_surveillance = stop_surveillance = get_alerts = get_surveillance_summary = _missing

    class AlertLevel:
        """Stub for AlertLevel when import fails."""
        pass

@click.group()
def surveillance():
    """Trading surveillance and market monitoring commands"""
    pass

@surveillance.command()
@click.option("--symbols", required=True, help="Trading symbols to monitor (comma-separated)")
@click.option("--duration", type=int, default=300, help="Monitoring duration in seconds")
@click.pass_context
def start(ctx, symbols: str, duration: int):
    """Start trading surveillance monitoring"""
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        
        click.echo(f"🔍 Starting trading surveillance...")
        click.echo(f"📊 Monitoring symbols: {', '.join(symbol_list)}")
        click.echo(f"⏱️  Duration: {duration} seconds")
        
        async def run_monitoring():
            # Start monitoring
            await start_surveillance(symbol_list)
            
            click.echo(f"✅ Surveillance started!")
            click.echo(f"🔍 Monitoring {len(symbol_list)} symbols for manipulation patterns")
            
            if duration > 0:
                click.echo(f"⏱️  Will run for {duration} seconds...")
                
                # Run for specified duration
                await asyncio.sleep(duration)
                
                # Stop monitoring
                await stop_surveillance()
                click.echo(f"🔍 Surveillance stopped after {duration} seconds")
                
                # Show results
                alerts = get_alerts()
                if alerts['total'] > 0:
                    click.echo(f"\n🚨 Generated {alerts['total']} alerts during monitoring:")
                    for alert in alerts['alerts'][:5]:  # Show first 5
                        level_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(alert['level'], "❓")
                        click.echo(f"  {level_icon} {alert['description'][:80]}...")
                else:
                    click.echo(f"\n✅ No alerts generated during monitoring period")
        
        # Run the async function
        asyncio.run(run_monitoring())
        
    except Exception as e:
        click.echo(f"❌ Failed to start surveillance: {e}", err=True)

@surveillance.command()
@click.pass_context
def stop(ctx):
    """Stop trading surveillance monitoring"""
    try:
        click.echo(f"🔍 Stopping trading surveillance...")
        
        success = asyncio.run(stop_surveillance())
        
        if success:
            click.echo(f"✅ Surveillance stopped successfully")
        else:
            click.echo(f"⚠️  Surveillance was not running")
        
    except Exception as e:
        click.echo(f"❌ Failed to stop surveillance: {e}", err=True)

@surveillance.command()
@click.option("--level", type=click.Choice(['critical', 'high', 'medium', 'low']), help="Filter by alert level")
@click.option("--limit", type=int, default=20, help="Maximum number of alerts to show")
@click.pass_context
def alerts(ctx, level: str, limit: int):
    """Show trading surveillance alerts"""
    try:
        click.echo(f"🚨 Trading Surveillance Alerts")
        
        alerts_data = get_alerts(level)
        
        if alerts_data['total'] == 0:
            click.echo(f"✅ No active alerts")
            return
        
        click.echo(f"\n📊 Total Active Alerts: {alerts_data['total']}")
        
        if level:
            click.echo(f"🔍 Filtered by level: {level.upper()}")
        
        # Display alerts
        for i, alert in enumerate(alerts_data['alerts'][:limit]):
            level_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(alert['level'], "❓")
            
            click.echo(f"\n{level_icon} Alert #{i+1}")
            click.echo(f"   ID: {alert['alert_id']}")
            click.echo(f"   Level: {alert['level'].upper()}")
            click.echo(f"   Description: {alert['description']}")
            click.echo(f"   Confidence: {alert['confidence']:.2f}")
            click.echo(f"   Risk Score: {alert['risk_score']:.2f}")
            click.echo(f"   Time: {alert['timestamp']}")
            
            if alert.get('manipulation_type'):
                click.echo(f"   Manipulation: {alert['manipulation_type'].replace('_', ' ').title()}")
            
            if alert.get('anomaly_type'):
                click.echo(f"   Anomaly: {alert['anomaly_type'].replace('_', ' ').title()}")
            
            if alert['affected_symbols']:
                click.echo(f"   Symbols: {', '.join(alert['affected_symbols'])}")
            
            if alert['affected_users']:
                click.echo(f"   Users: {', '.join(alert['affected_users'][:3])}")
                if len(alert['affected_users']) > 3:
                    click.echo(f"   ... and {len(alert['affected_users']) - 3} more")
        
        if alerts_data['total'] > limit:
            click.echo(f"\n... and {alerts_data['total'] - limit} more alerts")
        
    except Exception as e:
        click.echo(f"❌ Failed to get alerts: {e}", err=True)

@surveillance.command()
@click.pass_context
def summary(ctx):
    """Show surveillance summary and statistics"""
    try:
        click.echo(f"📊 Trading Surveillance Summary")
        
        summary = get_surveillance_summary()
        
        click.echo(f"\n📈 Alert Statistics:")
        click.echo(f"   Total Alerts: {summary['total_alerts']}")
        click.echo(f"   Active Alerts: {summary['active_alerts']}")
        
        click.echo(f"\n🎯 Alerts by Severity:")
        click.echo(f"   🔴 Critical: {summary['by_level']['critical']}")
        click.echo(f"   🟠 High: {summary['by_level']['high']}")
        click.echo(f"   🟡 Medium: {summary['by_level']['medium']}")
        click.echo(f"   🟢 Low: {summary['by_level']['low']}")
        
        click.echo(f"\n🔍 Alerts by Type:")
        click.echo(f"   Pump & Dump: {summary['by_type']['pump_and_dump']}")
        click.echo(f"   Wash Trading: {summary['by_type']['wash_trading']}")
        click.echo(f"   Spoofing: {summary['by_type']['spoofing']}")
        click.echo(f"   Volume Spikes: {summary['by_type']['volume_spike']}")
        click.echo(f"   Price Anomalies: {summary['by_type']['price_anomaly']}")
        click.echo(f"   Concentrated Trading: {summary['by_type']['concentrated_trading']}")
        
        click.echo(f"\n⚠️  Risk Distribution:")
        click.echo(f"   High Risk (>0.7): {summary['risk_distribution']['high_risk']}")
        click.echo(f"   Medium Risk (0.4-0.7): {summary['risk_distribution']['medium_risk']}")
        click.echo(f"   Low Risk (<0.4): {summary['risk_distribution']['low_risk']}")
        
        # Recommendations
        click.echo(f"\n💡 Recommendations:")
        
        if summary['by_level']['critical'] > 0:
            click.echo(f"   🚨 URGENT: {summary['by_level']['critical']} critical alerts require immediate attention")
        
        if summary['by_level']['high'] > 5:
            click.echo(f"   ⚠️  High alert volume ({summary['by_level']['high']}) - consider increasing monitoring")
        
        if summary['by_type']['pump_and_dump'] > 2:
            click.echo(f"   📈 Multiple pump & dump patterns detected - review market integrity")
        
        if summary['risk_distribution']['high_risk'] > 3:
            click.echo(f"   🔥 High risk activity detected - implement additional safeguards")
        
        if summary['active_alerts'] == 0:
            click.echo(f"   ✅ All clear - no suspicious activity detected")
        
    except Exception as e:
        click.echo(f"❌ Failed to get summary: {e}", err=True)

@surveillance.command()
@click.option("--alert-id", required=True, help="Alert ID to resolve")
@click.option("--resolution", default="resolved", type=click.Choice(['resolved', 'false_positive']), help="Resolution type")
@click.pass_context
def resolve(ctx, alert_id: str, resolution: str):
    """Resolve a surveillance alert"""
    try:
        click.echo(f"🔍 Resolving alert: {alert_id}")
        
        # Import surveillance to access resolve function
        from app.services.trading_surveillance import surveillance
        
        success = surveillance.resolve_alert(alert_id, resolution)
        
        if success:
            click.echo(f"✅ Alert {alert_id} marked as {resolution}")
        else:
            click.echo(f"❌ Alert {alert_id} not found")
        
    except Exception as e:
        click.echo(f"❌ Failed to resolve alert: {e}", err=True)

@surveillance.command()
@click.option("--symbols", required=True, help="Symbols to test (comma-separated)")
@click.option("--duration", type=int, default=10, help="Test duration in seconds")
@click.pass_context
def test(ctx, symbols: str, duration: int):
    """Run surveillance test with mock data"""
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        
        click.echo(f"🧪 Running surveillance test...")
        click.echo(f"📊 Testing symbols: {', '.join(symbol_list)}")
        click.echo(f"⏱️  Duration: {duration} seconds")
        
        # Import test function
        from app.services.trading_surveillance import test_trading_surveillance
        
        # Run test
        asyncio.run(test_trading_surveillance())
        
        # Show recent alerts
        alerts = get_alerts()
        click.echo(f"\n🚨 Test Results:")
        click.echo(f"   Total Alerts Generated: {alerts['total']}")
        
        if alerts['total'] > 0:
            click.echo(f"   Sample Alerts:")
            for alert in alerts['alerts'][:3]:
                level_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(alert['level'], "❓")
                click.echo(f"   {level_icon} {alert['description']}")
        
        click.echo(f"\n✅ Surveillance test complete!")
        
    except Exception as e:
        click.echo(f"❌ Test failed: {e}", err=True)

@surveillance.command()
@click.pass_context
def status(ctx):
    """Show current surveillance status"""
    try:
        from app.services.trading_surveillance import surveillance
        
        click.echo(f"📊 Trading Surveillance Status")
        
        if surveillance.is_monitoring:
            click.echo(f"🟢 Status: ACTIVE")
            click.echo(f"📊 Monitoring Symbols: {len(surveillance.monitoring_symbols)}")
            
            if surveillance.monitoring_symbols:
                click.echo(f"🔍 Active Symbols: {', '.join(surveillance.monitoring_symbols.keys())}")
            
            click.echo(f"📈 Total Alerts Generated: {len(surveillance.alerts)}")
            click.echo(f"🚨 Active Alerts: {len([a for a in surveillance.alerts if a.status == 'active'])}")
        else:
            click.echo(f"🔴 Status: INACTIVE")
            click.echo(f"💤 Surveillance is not currently running")
        
        click.echo(f"\n⚙️  Configuration:")
        click.echo(f"   Volume Spike Threshold: {surveillance.thresholds['volume_spike_multiplier']}x average")
        click.echo(f"   Price Change Threshold: {surveillance.thresholds['price_change_threshold']:.1%}")
        click.echo(f"   Wash Trade Threshold: {surveillance.thresholds['wash_trade_threshold']:.1%}")
        click.echo(f"   Spoofing Threshold: {surveillance.thresholds['spoofing_threshold']:.1%}")
        click.echo(f"   Concentration Threshold: {surveillance.thresholds['concentration_threshold']:.1%}")
        
    except Exception as e:
        click.echo(f"❌ Failed to get status: {e}", err=True)

@surveillance.command()
@click.pass_context
def list_patterns(ctx):
    """List detected manipulation patterns and anomalies"""
    try:
        click.echo(f"🔍 Trading Pattern Detection")
        
        patterns = {
            "Manipulation Patterns": [
                {
                    "name": "Pump and Dump",
                    "description": "Rapid price increase followed by sharp decline",
                    "indicators": ["Volume spikes", "Unusual price momentum", "Sudden reversals"],
                    "risk_level": "High"
                },
                {
                    "name": "Wash Trading",
                    "description": "Circular trading between same entities",
                    "indicators": ["High user concentration", "Repetitive trade patterns", "Low market impact"],
                    "risk_level": "High"
                },
                {
                    "name": "Spoofing",
                    "description": "Placing large orders with intent to cancel",
                    "indicators": ["High cancellation rate", "Large order sizes", "No execution"],
                    "risk_level": "Medium"
                },
                {
                    "name": "Layering",
                    "description": "Multiple non-executed orders at different prices",
                    "indicators": ["Ladder order patterns", "Rapid cancellations", "Price manipulation"],
                    "risk_level": "Medium"
                }
            ],
            "Anomaly Types": [
                {
                    "name": "Volume Spike",
                    "description": "Unusual increase in trading volume",
                    "indicators": ["3x+ average volume", "Sudden volume changes", "Unusual timing"],
                    "risk_level": "Medium"
                },
                {
                    "name": "Price Anomaly",
                    "description": "Unusual price movements",
                    "indicators": ["15%+ price changes", "Deviation from trend", "Gap movements"],
                    "risk_level": "Medium"
                },
                {
                    "name": "Concentrated Trading",
                    "description": "Trading dominated by few participants",
                    "indicators": ["High HHI index", "Single user dominance", "Unequal distribution"],
                    "risk_level": "Medium"
                },
                {
                    "name": "Unusual Timing",
                    "description": "Suspicious timing patterns",
                    "indicators": ["Off-hours activity", "Coordinated timing", "Predictable patterns"],
                    "risk_level": "Low"
                }
            ]
        }
        
        for category, pattern_list in patterns.items():
            click.echo(f"\n📋 {category}:")
            for pattern in pattern_list:
                risk_icon = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(pattern["risk_level"], "❓")
                click.echo(f"\n{risk_icon} {pattern['name']}")
                click.echo(f"   Description: {pattern['description']}")
                click.echo(f"   Indicators: {', '.join(pattern['indicators'])}")
                click.echo(f"   Risk Level: {pattern['risk_level']}")
        
        click.echo(f"\n💡 Detection Methods:")
        click.echo(f"   • Statistical analysis of trading patterns")
        click.echo(f"   • Machine learning anomaly detection")
        click.echo(f"   • Real-time monitoring and alerting")
        click.echo(f"   • Cross-market correlation analysis")
        click.echo(f"   • User behavior pattern analysis")
        
    except Exception as e:
        click.echo(f"❌ Failed to list patterns: {e}", err=True)

if __name__ == "__main__":
    surveillance()
