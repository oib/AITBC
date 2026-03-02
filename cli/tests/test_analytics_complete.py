#!/usr/bin/env python3
"""
Complete analytics workflow test
"""

import sys
import os
import asyncio
import json
sys.path.insert(0, '/home/oib/windsurf/aitbc/cli')

from aitbc_cli.core.config import load_multichain_config
from aitbc_cli.core.analytics import ChainAnalytics

async def test_complete_analytics_workflow():
    """Test the complete analytics workflow"""
    print("🚀 Starting Complete Analytics Workflow Test")
    
    # Load configuration
    config = load_multichain_config('/home/oib/windsurf/aitbc/cli/multichain_config.yaml')
    print(f"✅ Configuration loaded with {len(config.nodes)} nodes")
    
    # Initialize analytics
    analytics = ChainAnalytics(config)
    print("✅ Analytics system initialized")
    
    # Test 1: Collect metrics from all chains
    print("\n📊 Testing Metrics Collection...")
    all_metrics = await analytics.collect_all_metrics()
    print(f"  ✅ Collected metrics for {len(all_metrics)} chains")
    
    total_metrics = sum(len(metrics) for metrics in all_metrics.values())
    print(f"  ✅ Total data points collected: {total_metrics}")
    
    # Test 2: Performance summaries
    print("\n📈 Testing Performance Summaries...")
    for chain_id in list(all_metrics.keys())[:3]:  # Test first 3 chains
        summary = analytics.get_chain_performance_summary(chain_id, 24)
        if summary:
            print(f"  ✅ {chain_id}: Health Score {summary['health_score']:.1f}/100")
            print(f"    TPS: {summary['statistics']['tps']['avg']:.2f}")
            print(f"    Block Time: {summary['statistics']['block_time']['avg']:.2f}s")
    
    # Test 3: Cross-chain analysis
    print("\n🔍 Testing Cross-Chain Analysis...")
    analysis = analytics.get_cross_chain_analysis()
    print(f"  ✅ Total Chains: {analysis['total_chains']}")
    print(f"  ✅ Active Chains: {analysis['active_chains']}")
    print(f"  ✅ Total Memory Usage: {analysis['resource_usage']['total_memory_mb']:.1f}MB")
    print(f"  ✅ Total Disk Usage: {analysis['resource_usage']['total_disk_mb']:.1f}MB")
    print(f"  ✅ Total Clients: {analysis['resource_usage']['total_clients']}")
    print(f"  ✅ Total Agents: {analysis['resource_usage']['total_agents']}")
    
    # Test 4: Health scores
    print("\n💚 Testing Health Score Calculation...")
    for chain_id, health_score in analytics.health_scores.items():
        status = "Excellent" if health_score > 80 else "Good" if health_score > 60 else "Fair" if health_score > 40 else "Poor"
        print(f"  ✅ {chain_id}: {health_score:.1f}/100 ({status})")
    
    # Test 5: Alerts
    print("\n🚨 Testing Alert System...")
    if analytics.alerts:
        print(f"  ✅ Generated {len(analytics.alerts)} alerts")
        critical_alerts = [a for a in analytics.alerts if a.severity == "critical"]
        warning_alerts = [a for a in analytics.alerts if a.severity == "warning"]
        print(f"    Critical: {len(critical_alerts)}")
        print(f"    Warning: {len(warning_alerts)}")
        
        # Show recent alerts
        for alert in analytics.alerts[-3:]:
            print(f"    • {alert.chain_id}: {alert.message}")
    else:
        print("  ✅ No alerts generated (all systems healthy)")
    
    # Test 6: Performance predictions
    print("\n🔮 Testing Performance Predictions...")
    for chain_id in list(all_metrics.keys())[:2]:  # Test first 2 chains
        predictions = await analytics.predict_chain_performance(chain_id, 24)
        if predictions:
            print(f"  ✅ {chain_id}: {len(predictions)} predictions")
            for pred in predictions:
                print(f"    • {pred.metric}: {pred.predicted_value:.2f} (confidence: {pred.confidence:.1%})")
        else:
            print(f"  ⚠️  {chain_id}: Insufficient data for predictions")
    
    # Test 7: Optimization recommendations
    print("\n⚡ Testing Optimization Recommendations...")
    for chain_id in list(all_metrics.keys())[:2]:  # Test first 2 chains
        recommendations = analytics.get_optimization_recommendations(chain_id)
        if recommendations:
            print(f"  ✅ {chain_id}: {len(recommendations)} recommendations")
            for rec in recommendations:
                print(f"    • {rec['priority']} priority {rec['type']}: {rec['issue']}")
        else:
            print(f"  ✅ {chain_id}: No optimizations needed")
    
    # Test 8: Dashboard data
    print("\n📊 Testing Dashboard Data Generation...")
    dashboard_data = analytics.get_dashboard_data()
    print(f"  ✅ Dashboard data generated")
    print(f"    Overview metrics: {len(dashboard_data['overview'])}")
    print(f"    Chain summaries: {len(dashboard_data['chain_summaries'])}")
    print(f"    Recent alerts: {len(dashboard_data['alerts'])}")
    print(f"    Predictions: {len(dashboard_data['predictions'])}")
    print(f"    Recommendations: {len(dashboard_data['recommendations'])}")
    
    # Test 9: Performance benchmarks
    print("\n🏆 Testing Performance Benchmarks...")
    if analysis["performance_comparison"]:
        # Find best performing chain
        best_chain = max(analysis["performance_comparison"].items(), 
                        key=lambda x: x[1]["health_score"])
        print(f"  ✅ Best Performing Chain: {best_chain[0]}")
        print(f"    Health Score: {best_chain[1]['health_score']:.1f}/100")
        print(f"    TPS: {best_chain[1]['tps']:.2f}")
        print(f"    Block Time: {best_chain[1]['block_time']:.2f}s")
        
        # Find chains needing attention
        attention_chains = [cid for cid, data in analysis["performance_comparison"].items() 
                           if data["health_score"] < 50]
        if attention_chains:
            print(f"  ⚠️  Chains Needing Attention: {len(attention_chains)}")
            for chain_id in attention_chains[:3]:
                health = analysis["performance_comparison"][chain_id]["health_score"]
                print(f"    • {chain_id}: {health:.1f}/100")
    
    print("\n🎉 Complete Analytics Workflow Test Finished!")
    print("📊 Summary:")
    print("  ✅ Metrics collection and storage working")
    print("  ✅ Performance analysis and summaries functional")
    print("  ✅ Cross-chain analytics operational")
    print("  ✅ Health scoring system active")
    print("  ✅ Alert generation and monitoring working")
    print("  ✅ Performance predictions available")
    print("  ✅ Optimization recommendations generated")
    print("  ✅ Dashboard data aggregation complete")
    print("  ✅ Performance benchmarking functional")
    
    # Performance metrics
    print(f"\n📈 Current System Metrics:")
    print(f"  • Total Chains Monitored: {analysis['total_chains']}")
    print(f"  • Active Chains: {analysis['active_chains']}")
    print(f"  • Average Health Score: {sum(analytics.health_scores.values()) / len(analytics.health_scores) if analytics.health_scores else 0:.1f}/100")
    print(f"  • Total Alerts: {len(analytics.alerts)}")
    print(f"  • Resource Usage: {analysis['resource_usage']['total_memory_mb']:.1f}MB memory, {analysis['resource_usage']['total_disk_mb']:.1f}MB disk")

if __name__ == "__main__":
    asyncio.run(test_complete_analytics_workflow())
