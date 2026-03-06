"""Analytics and monitoring commands for AITBC CLI"""

import click
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from ..core.config import load_multichain_config
from ..core.analytics import ChainAnalytics
from ..utils import output, error, success

@click.group()
def analytics():
    """Chain analytics and monitoring commands"""
    pass

@analytics.command()
@click.option('--chain-id', help='Specific chain ID to analyze')
@click.option('--hours', default=24, help='Time range in hours')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def summary(ctx, chain_id, hours, format):
    """Get performance summary for chains"""
    try:
        config = load_multichain_config()
        analytics = ChainAnalytics(config)
        
        if chain_id:
            # Single chain summary
            summary = analytics.get_chain_performance_summary(chain_id, hours)
            if not summary:
                error(f"No data available for chain {chain_id}")
                raise click.Abort()
            
            # Format summary for display
            summary_data = [
                {"Metric": "Chain ID", "Value": summary["chain_id"]},
                {"Metric": "Time Range", "Value": f"{summary['time_range_hours']} hours"},
                {"Metric": "Data Points", "Value": summary["data_points"]},
                {"Metric": "Health Score", "Value": f"{summary['health_score']:.1f}/100"},
                {"Metric": "Active Alerts", "Value": summary["active_alerts"]},
                {"Metric": "Avg TPS", "Value": f"{summary['statistics']['tps']['avg']:.2f}"},
                {"Metric": "Avg Block Time", "Value": f"{summary['statistics']['block_time']['avg']:.2f}s"},
                {"Metric": "Avg Gas Price", "Value": f"{summary['statistics']['gas_price']['avg']:,} wei"}
            ]
            
            output(summary_data, ctx.obj.get('output_format', format), title=f"Chain Summary: {chain_id}")
        else:
            # Cross-chain analysis
            analysis = analytics.get_cross_chain_analysis()
            
            if not analysis:
                error("No analytics data available")
                raise click.Abort()
            
            # Overview data
            overview_data = [
                {"Metric": "Total Chains", "Value": analysis["total_chains"]},
                {"Metric": "Active Chains", "Value": analysis["active_chains"]},
                {"Metric": "Total Alerts", "Value": analysis["alerts_summary"]["total_alerts"]},
                {"Metric": "Critical Alerts", "Value": analysis["alerts_summary"]["critical_alerts"]},
                {"Metric": "Total Memory Usage", "Value": f"{analysis['resource_usage']['total_memory_mb']:.1f}MB"},
                {"Metric": "Total Disk Usage", "Value": f"{analysis['resource_usage']['total_disk_mb']:.1f}MB"},
                {"Metric": "Total Clients", "Value": analysis["resource_usage"]["total_clients"]},
                {"Metric": "Total Agents", "Value": analysis["resource_usage"]["total_agents"]}
            ]
            
            output(overview_data, ctx.obj.get('output_format', format), title="Cross-Chain Analysis Overview")
            
            # Performance comparison
            if analysis["performance_comparison"]:
                comparison_data = [
                    {
                        "Chain ID": chain_id,
                        "TPS": f"{data['tps']:.2f}",
                        "Block Time": f"{data['block_time']:.2f}s",
                        "Health Score": f"{data['health_score']:.1f}/100"
                    }
                    for chain_id, data in analysis["performance_comparison"].items()
                ]
                
                output(comparison_data, ctx.obj.get('output_format', format), title="Chain Performance Comparison")
        
    except Exception as e:
        error(f"Error getting analytics summary: {str(e)}")
        raise click.Abort()

@analytics.command()
@click.option('--realtime', is_flag=True, help='Real-time monitoring')
@click.option('--interval', default=30, help='Update interval in seconds')
@click.option('--chain-id', help='Monitor specific chain')
@click.pass_context
def monitor(ctx, realtime, interval, chain_id):
    """Monitor chain performance in real-time"""
    try:
        config = load_multichain_config()
        analytics = ChainAnalytics(config)
        
        if realtime:
            # Real-time monitoring
            from rich.console import Console
            from rich.live import Live
            from rich.table import Table
            import time
            
            console = Console()
            
            def generate_monitor_table():
                try:
                    # Collect latest metrics
                    asyncio.run(analytics.collect_all_metrics())
                    
                    table = Table(title=f"Chain Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    table.add_column("Chain ID", style="cyan")
                    table.add_column("TPS", style="green")
                    table.add_column("Block Time", style="yellow")
                    table.add_column("Health", style="red")
                    table.add_column("Alerts", style="magenta")
                    
                    if chain_id:
                        # Single chain monitoring
                        summary = analytics.get_chain_performance_summary(chain_id, 1)
                        if summary:
                            health_color = "green" if summary["health_score"] > 70 else "yellow" if summary["health_score"] > 40 else "red"
                            table.add_row(
                                chain_id,
                                f"{summary['statistics']['tps']['avg']:.2f}",
                                f"{summary['statistics']['block_time']['avg']:.2f}s",
                                f"[{health_color}]{summary['health_score']:.1f}[/{health_color}]",
                                str(summary["active_alerts"])
                            )
                    else:
                        # All chains monitoring
                        analysis = analytics.get_cross_chain_analysis()
                        for chain_id, data in analysis["performance_comparison"].items():
                            health_color = "green" if data["health_score"] > 70 else "yellow" if data["health_score"] > 40 else "red"
                            table.add_row(
                                chain_id,
                                f"{data['tps']:.2f}",
                                f"{data['block_time']:.2f}s",
                                f"[{health_color}]{data['health_score']:.1f}[/{health_color}]",
                                str(len([a for a in analytics.alerts if a.chain_id == chain_id]))
                            )
                    
                    return table
                except Exception as e:
                    return f"Error collecting metrics: {e}"
            
            with Live(generate_monitor_table(), refresh_per_second=1) as live:
                try:
                    while True:
                        live.update(generate_monitor_table())
                        time.sleep(interval)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Monitoring stopped by user[/yellow]")
        else:
            # Single snapshot
            asyncio.run(analytics.collect_all_metrics())
            
            if chain_id:
                summary = analytics.get_chain_performance_summary(chain_id, 1)
                if not summary:
                    error(f"No data available for chain {chain_id}")
                    raise click.Abort()
                
                monitor_data = [
                    {"Metric": "Chain ID", "Value": summary["chain_id"]},
                    {"Metric": "Current TPS", "Value": f"{summary['statistics']['tps']['avg']:.2f}"},
                    {"Metric": "Current Block Time", "Value": f"{summary['statistics']['block_time']['avg']:.2f}s"},
                    {"Metric": "Health Score", "Value": f"{summary['health_score']:.1f}/100"},
                    {"Metric": "Active Alerts", "Value": summary["active_alerts"]},
                    {"Metric": "Memory Usage", "Value": f"{summary['latest_metrics']['memory_usage_mb']:.1f}MB"},
                    {"Metric": "Disk Usage", "Value": f"{summary['latest_metrics']['disk_usage_mb']:.1f}MB"},
                    {"Metric": "Active Nodes", "Value": summary["latest_metrics"]["active_nodes"]},
                    {"Metric": "Client Count", "Value": summary["latest_metrics"]["client_count"]},
                    {"Metric": "Agent Count", "Value": summary["latest_metrics"]["agent_count"]}
                ]
                
                output(monitor_data, ctx.obj.get('output_format', 'table'), title=f"Chain Monitor: {chain_id}")
            else:
                analysis = analytics.get_cross_chain_analysis()
                
                monitor_data = [
                    {"Metric": "Total Chains", "Value": analysis["total_chains"]},
                    {"Metric": "Active Chains", "Value": analysis["active_chains"]},
                    {"Metric": "Total Memory Usage", "Value": f"{analysis['resource_usage']['total_memory_mb']:.1f}MB"},
                    {"Metric": "Total Disk Usage", "Value": f"{analysis['resource_usage']['total_disk_mb']:.1f}MB"},
                    {"Metric": "Total Clients", "Value": analysis["resource_usage"]["total_clients"]},
                    {"Metric": "Total Agents", "Value": analysis["resource_usage"]["total_agents"]},
                    {"Metric": "Total Alerts", "Value": analysis["alerts_summary"]["total_alerts"]},
                    {"Metric": "Critical Alerts", "Value": analysis["alerts_summary"]["critical_alerts"]}
                ]
                
                output(monitor_data, ctx.obj.get('output_format', 'table'), title="System Monitor")
        
    except Exception as e:
        error(f"Error during monitoring: {str(e)}")
        raise click.Abort()

@analytics.command()
@click.option('--chain-id', help='Specific chain ID for predictions')
@click.option('--hours', default=24, help='Prediction time horizon in hours')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def predict(ctx, chain_id, hours, format):
    """Predict chain performance"""
    try:
        config = load_multichain_config()
        analytics = ChainAnalytics(config)
        
        # Collect current metrics first
        asyncio.run(analytics.collect_all_metrics())
        
        if chain_id:
            # Single chain prediction
            predictions = asyncio.run(analytics.predict_chain_performance(chain_id, hours))
            
            if not predictions:
                error(f"No prediction data available for chain {chain_id}")
                raise click.Abort()
            
            prediction_data = [
                {
                    "Metric": pred.metric,
                    "Predicted Value": f"{pred.predicted_value:.2f}",
                    "Confidence": f"{pred.confidence:.1%}",
                    "Time Horizon": f"{pred.time_horizon_hours}h"
                }
                for pred in predictions
            ]
            
            output(prediction_data, ctx.obj.get('output_format', format), title=f"Performance Predictions: {chain_id}")
        else:
            # All chains prediction
            analysis = analytics.get_cross_chain_analysis()
            all_predictions = {}
            
            for chain_id in analysis["performance_comparison"].keys():
                predictions = asyncio.run(analytics.predict_chain_performance(chain_id, hours))
                if predictions:
                    all_predictions[chain_id] = predictions
            
            if not all_predictions:
                error("No prediction data available")
                raise click.Abort()
            
            # Format predictions for display
            prediction_data = []
            for chain_id, predictions in all_predictions.items():
                for pred in predictions:
                    prediction_data.append({
                        "Chain ID": chain_id,
                        "Metric": pred.metric,
                        "Predicted Value": f"{pred.predicted_value:.2f}",
                        "Confidence": f"{pred.confidence:.1%}",
                        "Time Horizon": f"{pred.time_horizon_hours}h"
                    })
            
            output(prediction_data, ctx.obj.get('output_format', format), title="Chain Performance Predictions")
        
    except Exception as e:
        error(f"Error generating predictions: {str(e)}")
        raise click.Abort()

@analytics.command()
@click.option('--chain-id', help='Specific chain ID for recommendations')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def optimize(ctx, chain_id, format):
    """Get optimization recommendations"""
    try:
        config = load_multichain_config()
        analytics = ChainAnalytics(config)
        
        # Collect current metrics first
        asyncio.run(analytics.collect_all_metrics())
        
        if chain_id:
            # Single chain recommendations
            recommendations = analytics.get_optimization_recommendations(chain_id)
            
            if not recommendations:
                success(f"No optimization recommendations for chain {chain_id}")
                return
            
            recommendation_data = [
                {
                    "Type": rec["type"],
                    "Priority": rec["priority"],
                    "Issue": rec["issue"],
                    "Current Value": rec["current_value"],
                    "Recommended Action": rec["recommended_action"],
                    "Expected Improvement": rec["expected_improvement"]
                }
                for rec in recommendations
            ]
            
            output(recommendation_data, ctx.obj.get('output_format', format), title=f"Optimization Recommendations: {chain_id}")
        else:
            # All chains recommendations
            analysis = analytics.get_cross_chain_analysis()
            all_recommendations = {}
            
            for chain_id in analysis["performance_comparison"].keys():
                recommendations = analytics.get_optimization_recommendations(chain_id)
                if recommendations:
                    all_recommendations[chain_id] = recommendations
            
            if not all_recommendations:
                success("No optimization recommendations available")
                return
            
            # Format recommendations for display
            recommendation_data = []
            for chain_id, recommendations in all_recommendations.items():
                for rec in recommendations:
                    recommendation_data.append({
                        "Chain ID": chain_id,
                        "Type": rec["type"],
                        "Priority": rec["priority"],
                        "Issue": rec["issue"],
                        "Current Value": rec["current_value"],
                        "Recommended Action": rec["recommended_action"]
                    })
            
            output(recommendation_data, ctx.obj.get('output_format', format), title="Chain Optimization Recommendations")
        
    except Exception as e:
        error(f"Error getting optimization recommendations: {str(e)}")
        raise click.Abort()

@analytics.command()
@click.option('--severity', type=click.Choice(['all', 'critical', 'warning']), default='all', help='Alert severity filter')
@click.option('--hours', default=24, help='Time range in hours')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def alerts(ctx, severity, hours, format):
    """View performance alerts"""
    try:
        config = load_multichain_config()
        analytics = ChainAnalytics(config)
        
        # Collect current metrics first
        asyncio.run(analytics.collect_all_metrics())
        
        # Filter alerts
        cutoff_time = datetime.now() - timedelta(hours=hours)
        filtered_alerts = [
            alert for alert in analytics.alerts 
            if alert.timestamp >= cutoff_time
        ]
        
        if severity != 'all':
            filtered_alerts = [a for a in filtered_alerts if a.severity == severity]
        
        if not filtered_alerts:
            success("No alerts found")
            return
        
        alert_data = [
            {
                "Chain ID": alert.chain_id,
                "Type": alert.alert_type,
                "Severity": alert.severity,
                "Message": alert.message,
                "Current Value": f"{alert.current_value:.2f}",
                "Threshold": f"{alert.threshold:.2f}",
                "Time": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            }
            for alert in filtered_alerts
        ]
        
        output(alert_data, ctx.obj.get('output_format', format), title=f"Performance Alerts (Last {hours}h)")
        
    except Exception as e:
        error(f"Error getting alerts: {str(e)}")
        raise click.Abort()

@analytics.command()
@click.option('--format', type=click.Choice(['json']), default='json', help='Output format')
@click.pass_context
def dashboard(ctx, format):
    """Get complete dashboard data"""
    try:
        config = load_multichain_config()
        analytics = ChainAnalytics(config)
        
        # Collect current metrics
        asyncio.run(analytics.collect_all_metrics())
        
        # Get dashboard data
        dashboard_data = analytics.get_dashboard_data()
        
        if format == 'json':
            import json
            click.echo(json.dumps(dashboard_data, indent=2, default=str))
        else:
            error("Dashboard data only available in JSON format")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error getting dashboard data: {str(e)}")
        raise click.Abort()
