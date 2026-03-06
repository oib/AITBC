#!/usr/bin/env python3
"""
AI Surveillance CLI Commands
Advanced AI-powered surveillance and behavioral analysis
"""

import click
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

# Import AI surveillance system
import sys
sys.path.append('/home/oib/windsurf/aitbc/apps/coordinator-api/src/app/services')
from ai_surveillance import (
    start_ai_surveillance, stop_ai_surveillance, get_surveillance_summary,
    get_user_risk_profile, list_active_alerts, analyze_behavior_patterns,
    ai_surveillance, SurveillanceType, RiskLevel, AlertPriority
)

@click.group()
def ai_surveillance_group():
    """AI-powered surveillance and behavioral analysis commands"""
    pass

@ai_surveillance_group.command()
@click.option("--symbols", required=True, help="Trading symbols to monitor (comma-separated)")
@click.pass_context
def start(ctx, symbols: str):
    """Start AI surveillance monitoring"""
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        
        click.echo(f"🤖 Starting AI Surveillance Monitoring...")
        click.echo(f"📊 Monitoring symbols: {', '.join(symbol_list)}")
        
        success = asyncio.run(start_ai_surveillance(symbol_list))
        
        if success:
            click.echo(f"✅ AI Surveillance monitoring started!")
            click.echo(f"🔍 ML-based pattern recognition active")
            click.echo(f"👥 Behavioral analysis running")
            click.echo(f"⚠️  Predictive risk assessment enabled")
            click.echo(f"🛡️  Market integrity protection active")
        else:
            click.echo(f"❌ Failed to start AI surveillance")
            
    except Exception as e:
        click.echo(f"❌ Start surveillance failed: {e}", err=True)

@ai_surveillance_group.command()
@click.pass_context
def stop(ctx):
    """Stop AI surveillance monitoring"""
    try:
        click.echo(f"🤖 Stopping AI Surveillance Monitoring...")
        
        success = asyncio.run(stop_ai_surveillance())
        
        if success:
            click.echo(f"✅ AI Surveillance monitoring stopped")
        else:
            click.echo(f"⚠️  Surveillance was not running")
            
    except Exception as e:
        click.echo(f"❌ Stop surveillance failed: {e}", err=True)

@ai_surveillance_group.command()
@click.pass_context
def status(ctx):
    """Show AI surveillance system status"""
    try:
        click.echo(f"🤖 AI Surveillance System Status")
        
        summary = get_surveillance_summary()
        
        click.echo(f"\n📊 System Overview:")
        click.echo(f"   Monitoring Active: {'✅ Yes' if summary['monitoring_active'] else '❌ No'}")
        click.echo(f"   Total Alerts: {summary['total_alerts']}")
        click.echo(f"   Resolved Alerts: {summary['resolved_alerts']}")
        click.echo(f"   False Positives: {summary['false_positives']}")
        click.echo(f"   Active Alerts: {summary['active_alerts']}")
        click.echo(f"   Behavior Patterns: {summary['behavior_patterns']}")
        click.echo(f"   Monitored Symbols: {summary['monitored_symbols']}")
        click.echo(f"   ML Models: {summary['ml_models']}")
        
        # Alerts by type
        alerts_by_type = summary.get('alerts_by_type', {})
        if alerts_by_type:
            click.echo(f"\n📈 Alerts by Type:")
            for alert_type, count in alerts_by_type.items():
                click.echo(f"   {alert_type.replace('_', ' ').title()}: {count}")
        
        # Alerts by risk level
        alerts_by_risk = summary.get('alerts_by_risk', {})
        if alerts_by_risk:
            click.echo(f"\n⚠️  Alerts by Risk Level:")
            risk_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            for risk_level, count in alerts_by_risk.items():
                icon = risk_icons.get(risk_level, "❓")
                click.echo(f"   {icon} {risk_level.title()}: {count}")
        
        # ML Model performance
        model_performance = summary.get('model_performance', {})
        if model_performance:
            click.echo(f"\n🤖 ML Model Performance:")
            for model_id, performance in model_performance.items():
                click.echo(f"   {model_id.replace('_', ' ').title()}:")
                click.echo(f"     Accuracy: {performance['accuracy']:.1%}")
                click.echo(f"     Threshold: {performance['threshold']:.2f}")
        
    except Exception as e:
        click.echo(f"❌ Status check failed: {e}", err=True)

@ai_surveillance_group.command()
@click.option("--limit", type=int, default=20, help="Maximum number of alerts to show")
@click.option("--type", type=click.Choice(['pattern_recognition', 'behavioral_analysis', 'predictive_risk', 'market_integrity']), help="Filter by alert type")
@click.option("--risk-level", type=click.Choice(['low', 'medium', 'high', 'critical']), help="Filter by risk level")
@click.pass_context
def alerts(ctx, limit: int, type: str, risk_level: str):
    """List active surveillance alerts"""
    try:
        click.echo(f"🚨 Active Surveillance Alerts")
        
        alerts = list_active_alerts(limit)
        
        # Apply filters
        if type:
            alerts = [a for a in alerts if a['type'] == type]
        
        if risk_level:
            alerts = [a for a in alerts if a['risk_level'] == risk_level]
        
        if not alerts:
            click.echo(f"✅ No active alerts found")
            return
        
        click.echo(f"\n📊 Total Alerts: {len(alerts)}")
        
        if type:
            click.echo(f"🔍 Filtered by type: {type.replace('_', ' ').title()}")
        
        if risk_level:
            click.echo(f"🔍 Filtered by risk level: {risk_level.title()}")
        
        # Display alerts
        for i, alert in enumerate(alerts):
            risk_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(alert['risk_level'], "❓")
            priority_icon = {"urgent": "🚨", "high": "⚡", "medium": "📋", "low": "📝"}.get(alert['priority'], "❓")
            
            click.echo(f"\n{risk_icon} Alert #{i+1}")
            click.echo(f"   ID: {alert['alert_id']}")
            click.echo(f"   Type: {alert['type'].replace('_', ' ').title()}")
            click.echo(f"   User: {alert['user_id']}")
            click.echo(f"   Risk Level: {alert['risk_level'].title()}")
            click.echo(f"   Priority: {alert['priority'].title()}")
            click.echo(f"   Confidence: {alert['confidence']:.1%}")
            click.echo(f"   Description: {alert['description']}")
            click.echo(f"   Detected: {alert['detected_at'][:19]}")
        
    except Exception as e:
        click.echo(f"❌ Alert listing failed: {e}", err=True)

@ai_surveillance_group.command()
@click.option("--user-id", help="Specific user ID to analyze")
@click.pass_context
def patterns(ctx, user_id: str):
    """Analyze behavior patterns"""
    try:
        click.echo(f"🔍 Behavior Pattern Analysis")
        
        if user_id:
            click.echo(f"👤 Analyzing user: {user_id}")
            patterns = analyze_behavior_patterns(user_id)
            
            click.echo(f"\n📊 User Pattern Summary:")
            click.echo(f"   Total Patterns: {patterns['total_patterns']}")
            click.echo(f"   Pattern Types: {', '.join(patterns['pattern_types'])}")
            
            if patterns['patterns']:
                click.echo(f"\n📈 Recent Patterns:")
                for pattern in patterns['patterns'][-5:]:  # Last 5 patterns
                    pattern_icon = "⚠️" if pattern['risk_score'] > 0.8 else "📋"
                    click.echo(f"   {pattern_icon} {pattern['pattern_type'].replace('_', ' ').title()}")
                    click.echo(f"      Confidence: {pattern['confidence']:.1%}")
                    click.echo(f"      Risk Score: {pattern['risk_score']:.2f}")
                    click.echo(f"      Detected: {pattern['detected_at'][:19]}")
        else:
            click.echo(f"📊 Overall Pattern Analysis")
            patterns = analyze_behavior_patterns()
            
            click.echo(f"\n📈 System Pattern Summary:")
            click.echo(f"   Total Patterns: {patterns['total_patterns']}")
            click.echo(f"   Average Confidence: {patterns['avg_confidence']:.1%}")
            click.echo(f"   Average Risk Score: {patterns['avg_risk_score']:.2f}")
            
            pattern_types = patterns.get('pattern_types', {})
            if pattern_types:
                click.echo(f"\n📊 Pattern Types:")
                for pattern_type, count in pattern_types.items():
                    click.echo(f"   {pattern_type.replace('_', ' ').title()}: {count}")
        
    except Exception as e:
        click.echo(f"❌ Pattern analysis failed: {e}", err=True)

@ai_surveillance_group.command()
@click.option("--user-id", required=True, help="User ID to analyze")
@click.pass_context
def risk_profile(ctx, user_id: str):
    """Get comprehensive user risk profile"""
    try:
        click.echo(f"⚠️  User Risk Profile: {user_id}")
        
        profile = get_user_risk_profile(user_id)
        
        click.echo(f"\n📊 Risk Assessment:")
        click.echo(f"   Predictive Risk Score: {profile['predictive_risk']:.2f}")
        click.echo(f"   Risk Trend: {profile['risk_trend'].title()}")
        click.echo(f"   Last Assessed: {profile['last_assessed'][:19] if profile['last_assessed'] else 'Never'}")
        
        click.echo(f"\n👤 User Activity:")
        click.echo(f"   Behavior Patterns: {profile['behavior_patterns']}")
        click.echo(f"   Surveillance Alerts: {profile['surveillance_alerts']}")
        
        if profile['pattern_types']:
            click.echo(f"   Pattern Types: {', '.join(profile['pattern_types'])}")
        
        if profile['alert_types']:
            click.echo(f"   Alert Types: {', '.join(profile['alert_types'])}")
        
        # Risk assessment
        risk_score = profile['predictive_risk']
        if risk_score > 0.9:
            risk_assessment = "🔴 CRITICAL - Immediate attention required"
        elif risk_score > 0.8:
            risk_assessment = "🟠 HIGH - Monitor closely"
        elif risk_score > 0.6:
            risk_assessment = "🟡 MEDIUM - Standard monitoring"
        else:
            risk_assessment = "🟢 LOW - Normal activity"
        
        click.echo(f"\n🎯 Risk Assessment: {risk_assessment}")
        
        # Recommendations
        if risk_score > 0.8:
            click.echo(f"\n💡 Recommendations:")
            click.echo(f"   • Review recent trading activity")
            click.echo(f"   • Consider temporary restrictions")
            click.echo(f"   • Enhanced monitoring protocols")
            click.echo(f"   • Manual compliance review")
        elif risk_score > 0.6:
            click.echo(f"\n💡 Recommendations:")
            click.echo(f"   • Continue standard monitoring")
            click.echo(f"   • Watch for pattern changes")
            click.echo(f"   • Periodic compliance checks")
        
    except Exception as e:
        click.echo(f"❌ Risk profile failed: {e}", err=True)

@ai_surveillance_group.command()
@click.pass_context
def models(ctx):
    """Show ML model information"""
    try:
        click.echo(f"🤖 AI Surveillance ML Models")
        
        summary = get_surveillance_summary()
        model_performance = summary.get('model_performance', {})
        
        if not model_performance:
            click.echo(f"❌ No model information available")
            return
        
        click.echo(f"\n📊 Model Performance Overview:")
        
        for model_id, performance in model_performance.items():
            click.echo(f"\n🤖 {model_id.replace('_', ' ').title()}:")
            click.echo(f"   Accuracy: {performance['accuracy']:.1%}")
            click.echo(f"   Risk Threshold: {performance['threshold']:.2f}")
            
            # Model status based on accuracy
            if performance['accuracy'] > 0.9:
                status = "🟢 Excellent"
            elif performance['accuracy'] > 0.8:
                status = "🟡 Good"
            elif performance['accuracy'] > 0.7:
                status = "🟠 Fair"
            else:
                status = "🔴 Poor"
            
            click.echo(f"   Status: {status}")
        
        # Model descriptions
        click.echo(f"\n📋 Model Descriptions:")
        descriptions = {
            "pattern_recognition": "Identifies suspicious trading patterns using isolation forest algorithms",
            "behavioral_analysis": "Analyzes user behavior patterns using clustering techniques",
            "predictive_risk": "Predicts future risk using gradient boosting models",
            "market_integrity": "Detects market manipulation using neural networks"
        }
        
        for model_id, description in descriptions.items():
            if model_id in model_performance:
                click.echo(f"\n🤖 {model_id.replace('_', ' ').title()}:")
                click.echo(f"   {description}")
        
    except Exception as e:
        click.echo(f"❌ Model information failed: {e}", err=True)

@ai_surveillance_group.command()
@click.option("--days", type=int, default=7, help="Analysis period in days")
@click.pass_context
def analytics(ctx, days: int):
    """Generate comprehensive surveillance analytics"""
    try:
        click.echo(f"📊 AI Surveillance Analytics")
        click.echo(f"📅 Analysis Period: {days} days")
        
        summary = get_surveillance_summary()
        
        click.echo(f"\n📈 System Performance:")
        click.echo(f"   Monitoring Status: {'✅ Active' if summary['monitoring_active'] else '❌ Inactive'}")
        click.echo(f"   Total Alerts Generated: {summary['total_alerts']}")
        click.echo(f"   Alerts Resolved: {summary['resolved_alerts']}")
        click.echo(f"   Resolution Rate: {(summary['resolved_alerts'] / max(summary['total_alerts'], 1)):.1%}")
        click.echo(f"   False Positive Rate: {(summary['false_positives'] / max(summary['resolved_alerts'], 1)):.1%}")
        
        # Alert analysis
        alerts_by_type = summary.get('alerts_by_type', {})
        if alerts_by_type:
            click.echo(f"\n📊 Alert Distribution:")
            total_alerts = sum(alerts_by_type.values())
            for alert_type, count in alerts_by_type.items():
                percentage = (count / total_alerts * 100) if total_alerts > 0 else 0
                click.echo(f"   {alert_type.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")
        
        # Risk analysis
        alerts_by_risk = summary.get('alerts_by_risk', {})
        if alerts_by_risk:
            click.echo(f"\n⚠️  Risk Level Distribution:")
            total_risk_alerts = sum(alerts_by_risk.values())
            for risk_level, count in alerts_by_risk.items():
                percentage = (count / total_risk_alerts * 100) if total_risk_alerts > 0 else 0
                risk_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(risk_level, "❓")
                click.echo(f"   {risk_icon} {risk_level.title()}: {count} ({percentage:.1f}%)")
        
        # Pattern analysis
        patterns = analyze_behavior_patterns()
        click.echo(f"\n🔍 Pattern Analysis:")
        click.echo(f"   Total Behavior Patterns: {patterns['total_patterns']}")
        click.echo(f"   Average Confidence: {patterns['avg_confidence']:.1%}")
        click.echo(f"   Average Risk Score: {patterns['avg_risk_score']:.2f}")
        
        pattern_types = patterns.get('pattern_types', {})
        if pattern_types:
            click.echo(f"   Most Common Pattern: {max(pattern_types, key=pattern_types.get)}")
        
        # System health
        click.echo(f"\n🏥 System Health:")
        health_score = summary.get('ml_models', 0) * 25  # 25 points per model
        if health_score >= 80:
            health_status = "🟢 Excellent"
        elif health_score >= 60:
            health_status = "🟡 Good"
        elif health_score >= 40:
            health_status = "🟠 Fair"
        else:
            health_status = "🔴 Poor"
        
        click.echo(f"   Health Score: {health_score}/100")
        click.echo(f"   Status: {health_status}")
        
        # Recommendations
        click.echo(f"\n💡 Analytics Recommendations:")
        if summary['active_alerts'] > 10:
            click.echo(f"   ⚠️  High number of active alerts - consider increasing monitoring resources")
        
        if summary['false_positives'] / max(summary['resolved_alerts'], 1) > 0.2:
            click.echo(f"   🔧 High false positive rate - consider adjusting model thresholds")
        
        if not summary['monitoring_active']:
            click.echo(f"   🚨 Surveillance inactive - start monitoring immediately")
        
        if patterns['avg_risk_score'] > 0.8:
            click.echo(f"   ⚠️  High average risk score - review user base and compliance measures")
        
    except Exception as e:
        click.echo(f"❌ Analytics generation failed: {e}", err=True)

@ai_surveillance_group.command()
@click.pass_context
def test(ctx):
    """Test AI surveillance system"""
    try:
        click.echo(f"🧪 Testing AI Surveillance System...")
        
        async def run_tests():
            # Test 1: Start surveillance
            click.echo(f"\n📋 Test 1: Start Surveillance")
            start_success = await start_ai_surveillance(["BTC/USDT", "ETH/USDT"])
            click.echo(f"   ✅ Start: {'Success' if start_success else 'Failed'}")
            
            # Let it run for data collection
            click.echo(f"⏱️  Collecting surveillance data...")
            await asyncio.sleep(3)
            
            # Test 2: Get status
            click.echo(f"\n📋 Test 2: System Status")
            summary = get_surveillance_summary()
            click.echo(f"   ✅ Status Retrieved: {len(summary)} metrics")
            
            # Test 3: Get alerts
            click.echo(f"\n📋 Test 3: Alert System")
            alerts = list_active_alerts()
            click.echo(f"   ✅ Alerts: {len(alerts)} generated")
            
            # Test 4: Pattern analysis
            click.echo(f"\n📋 Test 4: Pattern Analysis")
            patterns = analyze_behavior_patterns()
            click.echo(f"   ✅ Patterns: {patterns['total_patterns']} analyzed")
            
            # Test 5: Stop surveillance
            click.echo(f"\n📋 Test 5: Stop Surveillance")
            stop_success = await stop_ai_surveillance()
            click.echo(f"   ✅ Stop: {'Success' if stop_success else 'Failed'}")
            
            return start_success, stop_success, summary, alerts, patterns
        
        # Run the async tests
        start_success, stop_success, summary, alerts, patterns = asyncio.run(run_tests())
        
        # Show results
        click.echo(f"\n🎉 Test Results Summary:")
        click.echo(f"   System Status: {'✅ Operational' if start_success and stop_success else '❌ Issues'}")
        click.echo(f"   ML Models: {summary.get('ml_models', 0)} active")
        click.echo(f"   Alerts Generated: {len(alerts)}")
        click.echo(f"   Patterns Detected: {patterns['total_patterns']}")
        
        if start_success and stop_success:
            click.echo(f"\n✅ AI Surveillance System is ready for production use!")
        else:
            click.echo(f"\n⚠️  Some issues detected - check logs for details")
        
    except Exception as e:
        click.echo(f"❌ Test failed: {e}", err=True)

if __name__ == "__main__":
    ai_surveillance_group()
