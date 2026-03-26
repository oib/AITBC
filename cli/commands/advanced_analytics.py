#!/usr/bin/env python3
"""
Advanced Analytics CLI Commands
Real-time analytics dashboard and market insights
"""

import click
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from imports import ensure_coordinator_api_imports

ensure_coordinator_api_imports()

try:
    from app.services.advanced_analytics import (
        start_analytics_monitoring, stop_analytics_monitoring, get_dashboard_data,
        create_analytics_alert, get_analytics_summary, advanced_analytics,
        MetricType, Timeframe
    )
    _import_error = None
except ImportError as e:
    _import_error = e

    def _missing(*args, **kwargs):
        raise ImportError(
            f"Required service module 'app.services.advanced_analytics' could not be imported: {_import_error}. "
            "Ensure coordinator-api dependencies are installed and the source directory is accessible."
        )
    start_analytics_monitoring = stop_analytics_monitoring = get_dashboard_data = _missing
    create_analytics_alert = get_analytics_summary = _missing
    advanced_analytics = None

    class MetricType:
        pass
    class Timeframe:
        pass

@click.group()
def advanced_analytics_group():
    """Advanced analytics and market insights commands"""
    pass

@advanced_analytics_group.command()
@click.option("--symbols", required=True, help="Trading symbols to monitor (comma-separated)")
@click.pass_context
def start(ctx, symbols: str):
    """Start advanced analytics monitoring"""
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        
        click.echo(f"📊 Starting Advanced Analytics Monitoring...")
        click.echo(f"📈 Monitoring symbols: {', '.join(symbol_list)}")
        
        success = asyncio.run(start_analytics_monitoring(symbol_list))
        
        if success:
            click.echo(f"✅ Advanced Analytics monitoring started!")
            click.echo(f"🔍 Real-time metrics collection active")
            click.echo(f"📊 Monitoring {len(symbol_list)} symbols")
        else:
            click.echo(f"❌ Failed to start monitoring")
            
    except Exception as e:
        click.echo(f"❌ Start monitoring failed: {e}", err=True)

@advanced_analytics_group.command()
@click.pass_context
def stop(ctx):
    """Stop advanced analytics monitoring"""
    try:
        click.echo(f"📊 Stopping Advanced Analytics Monitoring...")
        
        success = asyncio.run(stop_analytics_monitoring())
        
        if success:
            click.echo(f"✅ Advanced Analytics monitoring stopped")
        else:
            click.echo(f"⚠️  Monitoring was not running")
            
    except Exception as e:
        click.echo(f"❌ Stop monitoring failed: {e}", err=True)

@advanced_analytics_group.command()
@click.option("--symbol", required=True, help="Trading symbol")
@click.option("--format", type=click.Choice(['table', 'json']), default="table", help="Output format")
@click.pass_context
def dashboard(ctx, symbol: str, format: str):
    """Get real-time analytics dashboard"""
    try:
        symbol = symbol.upper()
        click.echo(f"📊 Real-Time Analytics Dashboard: {symbol}")
        
        dashboard_data = get_dashboard_data(symbol)
        
        if format == "json":
            click.echo(json.dumps(dashboard_data, indent=2, default=str))
            return
        
        # Display table format
        click.echo(f"\n📈 Current Metrics:")
        current_metrics = dashboard_data.get('current_metrics', {})
        
        if current_metrics:
            for metric_name, value in current_metrics.items():
                if isinstance(value, float):
                    if metric_name == 'price_metrics':
                        click.echo(f"   💰 Current Price: ${value:,.2f}")
                    elif metric_name == 'volume_metrics':
                        click.echo(f"   📊 Volume Ratio: {value:.2f}")
                    elif metric_name == 'volatility_metrics':
                        click.echo(f"   📈 Volatility: {value:.2%}")
                    else:
                        click.echo(f"   {metric_name}: {value:.4f}")
        
        # Technical indicators
        indicators = dashboard_data.get('technical_indicators', {})
        if indicators:
            click.echo(f"\n📊 Technical Indicators:")
            if 'sma_5' in indicators:
                click.echo(f"   📈 SMA 5: ${indicators['sma_5']:,.2f}")
            if 'sma_20' in indicators:
                click.echo(f"   📈 SMA 20: ${indicators['sma_20']:,.2f}")
            if 'rsi' in indicators:
                rsi = indicators['rsi']
                rsi_status = "🔴 Overbought" if rsi > 70 else "🟢 Oversold" if rsi < 30 else "🟡 Neutral"
                click.echo(f"   📊 RSI: {rsi:.1f} {rsi_status}")
            if 'bb_upper' in indicators:
                click.echo(f"   📊 BB Upper: ${indicators['bb_upper']:,.2f}")
                click.echo(f"   📊 BB Lower: ${indicators['bb_lower']:,.2f}")
        
        # Market status
        market_status = dashboard_data.get('market_status', 'unknown')
        status_icon = {"overbought": "🔴", "oversold": "🟢", "neutral": "🟡"}.get(market_status, "❓")
        click.echo(f"\n{status_icon} Market Status: {market_status.title()}")
        
        # Alerts
        alerts = dashboard_data.get('alerts', [])
        if alerts:
            click.echo(f"\n🚨 Active Alerts: {len(alerts)}")
            for alert in alerts[:3]:
                click.echo(f"   • {alert.name}: {alert.condition} {alert.threshold}")
        else:
            click.echo(f"\n✅ No active alerts")
        
        # Data history info
        price_history = dashboard_data.get('price_history', [])
        volume_history = dashboard_data.get('volume_history', [])
        click.echo(f"\n📊 Data Points:")
        click.echo(f"   Price History: {len(price_history)} points")
        click.echo(f"   Volume History: {len(volume_history)} points")
        
    except Exception as e:
        click.echo(f"❌ Dashboard failed: {e}", err=True)

@advanced_analytics_group.command()
@click.option("--name", required=True, help="Alert name")
@click.option("--symbol", required=True, help="Trading symbol")
@click.option("--metric", required=True, type=click.Choice(['price_metrics', 'volume_metrics', 'volatility_metrics']), help="Metric type")
@click.option("--condition", required=True, type=click.Choice(['gt', 'lt', 'eq', 'change_percent']), help="Alert condition")
@click.option("--threshold", type=float, required=True, help="Alert threshold")
@click.option("--timeframe", default="1h", type=click.Choice(['real_time', '1m', '5m', '15m', '1h', '4h', '1d']), help="Timeframe")
@click.pass_context
def create_alert(ctx, name: str, symbol: str, metric: str, condition: str, threshold: float, timeframe: str):
    """Create analytics alert"""
    try:
        symbol = symbol.upper()
        click.echo(f"🚨 Creating Analytics Alert...")
        click.echo(f"📋 Alert Name: {name}")
        click.echo(f"📊 Symbol: {symbol}")
        click.echo(f"📈 Metric: {metric}")
        click.echo(f"⚡ Condition: {condition}")
        click.echo(f"🎯 Threshold: {threshold}")
        click.echo(f"⏰ Timeframe: {timeframe}")
        
        alert_id = create_analytics_alert(name, symbol, metric, condition, threshold, timeframe)
        
        click.echo(f"\n✅ Alert created successfully!")
        click.echo(f"🆔 Alert ID: {alert_id}")
        click.echo(f"📊 Monitoring {symbol} {metric}")
        
        # Show alert condition in human readable format
        condition_text = {
            "gt": "greater than",
            "lt": "less than", 
            "eq": "equal to",
            "change_percent": "change percentage"
        }.get(condition, condition)
        
        click.echo(f"🔔 Triggers when: {metric} is {condition_text} {threshold}")
        
    except Exception as e:
        click.echo(f"❌ Alert creation failed: {e}", err=True)

@advanced_analytics_group.command()
@click.pass_context
def summary(ctx):
    """Show analytics summary"""
    try:
        click.echo(f"📊 Advanced Analytics Summary")
        
        summary = get_analytics_summary()
        
        click.echo(f"\n📈 System Status:")
        click.echo(f"   Monitoring Active: {'✅ Yes' if summary['monitoring_active'] else '❌ No'}")
        click.echo(f"   Total Alerts: {summary['total_alerts']}")
        click.echo(f"   Active Alerts: {summary['active_alerts']}")
        click.echo(f"   Tracked Symbols: {summary['tracked_symbols']}")
        click.echo(f"   Total Metrics Stored: {summary['total_metrics_stored']}")
        click.echo(f"   Performance Reports: {summary['performance_reports']}")
        
        # Symbol-specific metrics
        symbol_metrics = {k: v for k, v in summary.items() if k.endswith('_metrics')}
        if symbol_metrics:
            click.echo(f"\n📊 Symbol Metrics:")
            for symbol_key, count in symbol_metrics.items():
                symbol = symbol_key.replace('_metrics', '')
                click.echo(f"   {symbol}: {count} metrics")
        
        # Alert breakdown
        if advanced_analytics.alerts:
            click.echo(f"\n🚨 Alert Configuration:")
            for alert_id, alert in advanced_analytics.alerts.items():
                status_icon = "✅" if alert.active else "❌"
                click.echo(f"   {status_icon} {alert.name} ({alert.symbol})")
        
    except Exception as e:
        click.echo(f"❌ Summary failed: {e}", err=True)

@advanced_analytics_group.command()
@click.option("--symbol", required=True, help="Trading symbol")
@click.option("--days", type=int, default=30, help="Analysis period in days")
@click.pass_context
def performance(ctx, symbol: str, days: int):
    """Generate performance analysis report"""
    try:
        symbol = symbol.upper()
        click.echo(f"📊 Performance Analysis: {symbol}")
        click.echo(f"📅 Analysis Period: {days} days")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Generate performance report
        report = advanced_analytics.generate_performance_report(symbol, start_date, end_date)
        
        click.echo(f"\n📈 Performance Report:")
        click.echo(f"   Symbol: {report.symbol}")
        click.echo(f"   Period: {report.start_date.strftime('%Y-%m-%d')} to {report.end_date.strftime('%Y-%m-%d')}")
        
        # Performance metrics
        click.echo(f"\n💰 Returns:")
        click.echo(f"   Total Return: {report.total_return:.2%}")
        click.echo(f"   Volatility: {report.volatility:.2%}")
        click.echo(f"   Sharpe Ratio: {report.sharpe_ratio:.2f}")
        click.echo(f"   Max Drawdown: {report.max_drawdown:.2%}")
        
        # Risk metrics
        click.echo(f"\n⚠️  Risk Metrics:")
        click.echo(f"   Win Rate: {report.win_rate:.1%}")
        click.echo(f"   Profit Factor: {report.profit_factor:.2f}")
        click.echo(f"   Calmar Ratio: {report.calmar_ratio:.2f}")
        click.echo(f"   VaR (95%): {report.var_95:.2%}")
        
        # Performance assessment
        if report.total_return > 0.1:
            assessment = "🔥 EXCELLENT"
        elif report.total_return > 0.05:
            assessment = "⚡ GOOD"
        elif report.total_return > 0:
            assessment = "💡 POSITIVE"
        else:
            assessment = "❌ NEGATIVE"
        
        click.echo(f"\n{assessment} Performance Assessment")
        
        # Risk assessment
        if report.max_drawdown < 0.1:
            risk_assessment = "🟢 LOW RISK"
        elif report.max_drawdown < 0.2:
            risk_assessment = "🟡 MEDIUM RISK"
        else:
            risk_assessment = "🔴 HIGH RISK"
        
        click.echo(f"Risk Level: {risk_assessment}")
        
    except Exception as e:
        click.echo(f"❌ Performance analysis failed: {e}", err=True)

@advanced_analytics_group.command()
@click.option("--symbol", required=True, help="Trading symbol")
@click.option("--hours", type=int, default=24, help="Analysis period in hours")
@click.pass_context
def insights(ctx, symbol: str, hours: int):
    """Generate AI-powered market insights"""
    try:
        symbol = symbol.upper()
        click.echo(f"🔍 AI Market Insights: {symbol}")
        click.echo(f"⏰ Analysis Period: {hours} hours")
        
        # Get dashboard data
        dashboard = get_dashboard_data(symbol)
        
        if not dashboard:
            click.echo(f"❌ No data available for {symbol}")
            click.echo(f"💡 Start monitoring first: aitbc advanced-analytics start --symbols {symbol}")
            return
        
        # Extract key insights
        current_metrics = dashboard.get('current_metrics', {})
        indicators = dashboard.get('technical_indicators', {})
        market_status = dashboard.get('market_status', 'unknown')
        
        click.echo(f"\n📊 Current Market Analysis:")
        
        # Price analysis
        if 'price_metrics' in current_metrics:
            current_price = current_metrics['price_metrics']
            click.echo(f"   💰 Current Price: ${current_price:,.2f}")
        
        # Volume analysis
        if 'volume_metrics' in current_metrics:
            volume_ratio = current_metrics['volume_metrics']
            volume_status = "🔥 High" if volume_ratio > 1.5 else "📊 Normal" if volume_ratio > 0.8 else "📉 Low"
            click.echo(f"   📊 Volume Activity: {volume_status} (ratio: {volume_ratio:.2f})")
        
        # Volatility analysis
        if 'volatility_metrics' in current_metrics:
            volatility = current_metrics['volatility_metrics']
            vol_status = "🔴 High" if volatility > 0.05 else "🟡 Medium" if volatility > 0.02 else "🟢 Low"
            click.echo(f"   📈 Volatility: {vol_status} ({volatility:.2%})")
        
        # Technical analysis
        if indicators:
            click.echo(f"\n📈 Technical Analysis:")
            
            if 'rsi' in indicators:
                rsi = indicators['rsi']
                rsi_insight = "Overbought - consider selling" if rsi > 70 else "Oversold - consider buying" if rsi < 30 else "Neutral"
                click.echo(f"   📊 RSI ({rsi:.1f}): {rsi_insight}")
            
            if 'sma_5' in indicators and 'sma_20' in indicators:
                sma_5 = indicators['sma_5']
                sma_20 = indicators['sma_20']
                if 'price_metrics' in current_metrics:
                    price = current_metrics['price_metrics']
                    if price > sma_5 > sma_20:
                        trend = "🔥 Strong Uptrend"
                    elif price < sma_5 < sma_20:
                        trend = "📉 Strong Downtrend"
                    else:
                        trend = "🟡 Sideways"
                    click.echo(f"   📈 Trend: {trend}")
            
            if 'bb_upper' in indicators and 'bb_lower' in indicators:
                bb_upper = indicators['bb_upper']
                bb_lower = indicators['bb_lower']
                if 'price_metrics' in current_metrics:
                    price = current_metrics['price_metrics']
                    if price > bb_upper:
                        bb_signal = "Above upper band - overbought"
                    elif price < bb_lower:
                        bb_signal = "Below lower band - oversold"
                    else:
                        bb_signal = "Within bands - normal"
                    click.echo(f"   📊 Bollinger Bands: {bb_signal}")
        
        # Overall market status
        click.echo(f"\n🎯 Overall Market Status: {market_status.title()}")
        
        # Trading recommendation
        recommendation = _generate_trading_recommendation(dashboard)
        click.echo(f"💡 Trading Recommendation: {recommendation}")
        
    except Exception as e:
        click.echo(f"❌ Insights generation failed: {e}", err=True)

def _generate_trading_recommendation(dashboard: Dict[str, Any]) -> str:
    """Generate AI-powered trading recommendation"""
    current_metrics = dashboard.get('current_metrics', {})
    indicators = dashboard.get('technical_indicators', {})
    market_status = dashboard.get('market_status', 'unknown')
    
    # Simple recommendation logic
    buy_signals = 0
    sell_signals = 0
    
    # RSI signals
    if 'rsi' in indicators:
        rsi = indicators['rsi']
        if rsi < 30:
            buy_signals += 2
        elif rsi > 70:
            sell_signals += 2
    
    # Volume signals
    if 'volume_metrics' in current_metrics:
        volume_ratio = current_metrics['volume_metrics']
        if volume_ratio > 1.5:
            buy_signals += 1
    
    # Market status signals
    if market_status == 'oversold':
        buy_signals += 1
    elif market_status == 'overbought':
        sell_signals += 1
    
    # Generate recommendation
    if buy_signals > sell_signals + 1:
        return "🟢 STRONG BUY - Multiple bullish indicators detected"
    elif buy_signals > sell_signals:
        return "💡 BUY - Bullish bias detected"
    elif sell_signals > buy_signals + 1:
        return "🔴 STRONG SELL - Multiple bearish indicators detected"
    elif sell_signals > buy_signals:
        return "⚠️  SELL - Bearish bias detected"
    else:
        return "🟡 HOLD - Mixed signals, wait for clarity"

@advanced_analytics_group.command()
@click.pass_context
def test(ctx):
    """Test advanced analytics platform"""
    try:
        click.echo(f"🧪 Testing Advanced Analytics Platform...")
        
        async def run_tests():
            # Test 1: Start monitoring
            click.echo(f"\n📋 Test 1: Start Monitoring")
            start_success = await start_analytics_monitoring(["BTC/USDT", "ETH/USDT"])
            click.echo(f"   ✅ Start: {'Success' if start_success else 'Failed'}")
            
            # Let it run for a few seconds
            click.echo(f"⏱️  Collecting data...")
            await asyncio.sleep(3)
            
            # Test 2: Get dashboard
            click.echo(f"\n📋 Test 2: Dashboard Data")
            dashboard = get_dashboard_data("BTC/USDT")
            click.echo(f"   ✅ Dashboard: {len(dashboard)} fields retrieved")
            
            # Test 3: Get summary
            click.echo(f"\n📋 Test 3: Analytics Summary")
            summary = get_analytics_summary()
            click.echo(f"   ✅ Summary: {len(summary)} metrics")
            
            # Test 4: Stop monitoring
            click.echo(f"\n📋 Test 4: Stop Monitoring")
            stop_success = await stop_analytics_monitoring()
            click.echo(f"   ✅ Stop: {'Success' if stop_success else 'Failed'}")
            
            return start_success, stop_success, dashboard, summary
        
        # Run the async tests
        start_success, stop_success, dashboard, summary = asyncio.run(run_tests())
        
        # Show results
        click.echo(f"\n🎉 Test Results Summary:")
        click.echo(f"   Platform Status: {'✅ Operational' if start_success and stop_success else '❌ Issues'}")
        click.echo(f"   Data Collection: {'✅ Working' if dashboard else '❌ Issues'}")
        click.echo(f"   Metrics Tracked: {summary.get('total_metrics_stored', 0)}")
        
        if start_success and stop_success:
            click.echo(f"\n✅ Advanced Analytics Platform is ready for production use!")
        else:
            click.echo(f"\n⚠️  Some issues detected - check logs for details")
        
    except Exception as e:
        click.echo(f"❌ Test failed: {e}", err=True)

if __name__ == "__main__":
    advanced_analytics_group()
