"""Autonomous optimization commands for AITBC CLI"""

import click
import httpx
import json
import time
from typing import Optional, Dict, Any, List
from utils import output, error, success, warning


@click.group()
def optimize():
    """Autonomous optimization and predictive operations"""
    pass


@click.group()
def self_opt():
    """Self-optimization operations"""
    pass


optimize.add_command(self_opt)


@self_opt.command()
@click.argument("agent_id")
@click.option("--mode", default="auto-tune", 
              type=click.Choice(["auto-tune", "self-healing", "performance"]),
              help="Optimization mode")
@click.option("--scope", default="full", 
              type=click.Choice(["full", "performance", "cost", "latency"]),
              help="Optimization scope")
@click.option("--aggressiveness", default="moderate", 
              type=click.Choice(["conservative", "moderate", "aggressive"]),
              help="Optimization aggressiveness")
@click.pass_context
def enable(ctx, agent_id: str, mode: str, scope: str, aggressiveness: str):
    """Enable autonomous optimization for agent"""
    config = ctx.obj['config']
    
    optimization_config = {
        "mode": mode,
        "scope": scope,
        "aggressiveness": aggressiveness
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/optimize/agents/{agent_id}/enable",
                headers={"X-Api-Key": config.api_key or ""},
                json=optimization_config
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Autonomous optimization enabled for agent {agent_id}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to enable optimization: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@self_opt.command()
@click.argument("agent_id")
@click.option("--metrics", default="performance,cost", help="Comma-separated metrics to monitor")
@click.option("--real-time", is_flag=True, help="Show real-time optimization status")
@click.option("--interval", default=10, help="Update interval for real-time monitoring")
@click.pass_context
def status(ctx, agent_id: str, metrics: str, real_time: bool, interval: int):
    """Monitor optimization progress and status"""
    config = ctx.obj['config']
    
    params = {"metrics": [m.strip() for m in metrics.split(',')]}
    
    def get_status():
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{config.coordinator_url}/optimize/agents/{agent_id}/status",
                    headers={"X-Api-Key": config.api_key or ""},
                    params=params
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    error(f"Failed to get optimization status: {response.status_code}")
                    return None
        except Exception as e:
            error(f"Network error: {e}")
            return None
    
    if real_time:
        click.echo(f"Monitoring optimization for agent {agent_id} (Ctrl+C to stop)...")
        while True:
            status_data = get_status()
            if status_data:
                click.clear()
                click.echo(f"Optimization Status: {status_data.get('status', 'Unknown')}")
                click.echo(f"Mode: {status_data.get('mode', 'N/A')}")
                click.echo(f"Progress: {status_data.get('progress', 0)}%")
                
                metrics_data = status_data.get('metrics', {})
                for metric in [m.strip() for m in metrics.split(',')]:
                    if metric in metrics_data:
                        value = metrics_data[metric]
                        click.echo(f"{metric.title()}: {value}")
                
                if status_data.get('status') in ['completed', 'failed', 'disabled']:
                    break
            
            time.sleep(interval)
    else:
        status_data = get_status()
        if status_data:
            output(status_data, ctx.obj['output_format'])


@self_opt.command()
@click.argument("agent_id")
@click.option("--targets", required=True, help="Comma-separated target metrics (e.g., latency:100ms,cost:0.5)")
@click.option("--priority", default="balanced", 
              type=click.Choice(["performance", "cost", "balanced"]),
              help="Optimization priority")
@click.pass_context
def objectives(ctx, agent_id: str, targets: str, priority: str):
    """Set optimization objectives and targets"""
    config = ctx.obj['config']
    
    # Parse targets
    target_dict = {}
    for target in targets.split(','):
        if ':' in target:
            key, value = target.split(':', 1)
            target_dict[key.strip()] = value.strip()
        else:
            target_dict[target.strip()] = "optimize"
    
    objectives_data = {
        "targets": target_dict,
        "priority": priority
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/optimize/agents/{agent_id}/objectives",
                headers={"X-Api-Key": config.api_key or ""},
                json=objectives_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Optimization objectives set for agent {agent_id}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to set objectives: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@self_opt.command()
@click.argument("agent_id")
@click.option("--priority", default="all", 
              type=click.Choice(["high", "medium", "low", "all"]),
              help="Filter recommendations by priority")
@click.option("--category", help="Filter by category (performance, cost, security)")
@click.pass_context
def recommendations(ctx, agent_id: str, priority: str, category: Optional[str]):
    """Get optimization recommendations"""
    config = ctx.obj['config']
    
    params = {}
    if priority != "all":
        params["priority"] = priority
    if category:
        params["category"] = category
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/optimize/agents/{agent_id}/recommendations",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                recommendations = response.json()
                output(recommendations, ctx.obj['output_format'])
            else:
                error(f"Failed to get recommendations: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@self_opt.command()
@click.argument("agent_id")
@click.option("--recommendation-id", required=True, help="Specific recommendation ID to apply")
@click.option("--confirm", is_flag=True, help="Apply without confirmation prompt")
@click.pass_context
def apply(ctx, agent_id: str, recommendation_id: str, confirm: bool):
    """Apply optimization recommendation"""
    config = ctx.obj['config']
    
    if not confirm:
        if not click.confirm(f"Apply recommendation {recommendation_id} to agent {agent_id}?"):
            click.echo("Operation cancelled")
            return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/optimize/agents/{agent_id}/apply/{recommendation_id}",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Optimization recommendation applied")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to apply recommendation: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def predict():
    """Predictive operations"""
    pass


optimize.add_command(predict)

@predict.command()
@click.argument("agent_id")
@click.option("--horizon", default=24, help="Prediction horizon in hours")
@click.option("--resources", default="gpu,memory", help="Comma-separated resources to predict")
@click.option("--confidence", default=0.8, help="Minimum confidence threshold")
@click.pass_context
def predict(ctx, agent_id: str, horizon: int, resources: str, confidence: float):
    """Predict resource needs and usage patterns"""
    config = ctx.obj['config']
    
    prediction_data = {
        "horizon_hours": horizon,
        "resources": [r.strip() for r in resources.split(',')],
        "confidence_threshold": confidence
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/predict/agents/{agent_id}/resources",
                headers={"X-Api-Key": config.api_key or ""},
                json=prediction_data
            )
            
            if response.status_code == 200:
                predictions = response.json()
                success("Resource prediction completed")
                output(predictions, ctx.obj['output_format'])
            else:
                error(f"Failed to generate predictions: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.argument("agent_id")
@click.option("--policy", default="cost-efficiency", 
              type=click.Choice(["cost-efficiency", "performance", "availability", "hybrid"]),
              help="Auto-scaling policy")
@click.option("--min-instances", default=1, help="Minimum number of instances")
@click.option("--max-instances", default=10, help="Maximum number of instances")
@click.option("--cooldown", default=300, help="Cooldown period in seconds")
@click.pass_context
def autoscale(ctx, agent_id: str, policy: str, min_instances: int, max_instances: int, cooldown: int):
    """Configure auto-scaling based on predictions"""
    config = ctx.obj['config']
    
    autoscale_config = {
        "policy": policy,
        "min_instances": min_instances,
        "max_instances": max_instances,
        "cooldown_seconds": cooldown
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/predict/agents/{agent_id}/autoscale",
                headers={"X-Api-Key": config.api_key or ""},
                json=autoscale_config
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Auto-scaling configured for agent {agent_id}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to configure auto-scaling: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.argument("agent_id")
@click.option("--metric", required=True, help="Metric to forecast (throughput, latency, cost, etc.)")
@click.option("--period", default=7, help="Forecast period in days")
@click.option("--granularity", default="hour", 
              type=click.Choice(["minute", "hour", "day", "week"]),
              help="Forecast granularity")
@click.pass_context
def forecast(ctx, agent_id: str, metric: str, period: int, granularity: str):
    """Generate performance forecasts"""
    config = ctx.obj['config']
    
    forecast_params = {
        "metric": metric,
        "period_days": period,
        "granularity": granularity
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/predict/agents/{agent_id}/forecast",
                headers={"X-Api-Key": config.api_key or ""},
                json=forecast_params
            )
            
            if response.status_code == 200:
                forecast_data = response.json()
                success(f"Forecast generated for {metric}")
                output(forecast_data, ctx.obj['output_format'])
            else:
                error(f"Failed to generate forecast: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def tune():
    """Auto-tuning operations"""
    pass


optimize.add_command(tune)


@tune.command()
@click.argument("agent_id")
@click.option("--parameters", help="Comma-separated parameters to tune")
@click.option("--objective", default="performance", help="Optimization objective")
@click.option("--iterations", default=100, help="Number of tuning iterations")
@click.pass_context
def auto(ctx, agent_id: str, parameters: Optional[str], objective: str, iterations: int):
    """Start automatic parameter tuning"""
    config = ctx.obj['config']
    
    tuning_data = {
        "objective": objective,
        "iterations": iterations
    }
    
    if parameters:
        tuning_data["parameters"] = [p.strip() for p in parameters.split(',')]
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/tune/agents/{agent_id}/auto",
                headers={"X-Api-Key": config.api_key or ""},
                json=tuning_data
            )
            
            if response.status_code == 202:
                tuning = response.json()
                success(f"Auto-tuning started: {tuning['id']}")
                output(tuning, ctx.obj['output_format'])
            else:
                error(f"Failed to start auto-tuning: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@tune.command()
@click.argument("tuning_id")
@click.option("--watch", is_flag=True, help="Watch tuning progress")
@click.pass_context
def status(ctx, tuning_id: str, watch: bool):
    """Get auto-tuning status"""
    config = ctx.obj['config']
    
    def get_status():
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{config.coordinator_url}/tune/sessions/{tuning_id}",
                    headers={"X-Api-Key": config.api_key or ""}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    error(f"Failed to get tuning status: {response.status_code}")
                    return None
        except Exception as e:
            error(f"Network error: {e}")
            return None
    
    if watch:
        click.echo(f"Watching tuning session {tuning_id} (Ctrl+C to stop)...")
        while True:
            status_data = get_status()
            if status_data:
                click.clear()
                click.echo(f"Tuning Status: {status_data.get('status', 'Unknown')}")
                click.echo(f"Progress: {status_data.get('progress', 0)}%")
                click.echo(f"Iteration: {status_data.get('current_iteration', 0)}/{status_data.get('total_iterations', 0)}")
                click.echo(f"Best Score: {status_data.get('best_score', 'N/A')}")
                
                if status_data.get('status') in ['completed', 'failed', 'cancelled']:
                    break
            
            time.sleep(5)
    else:
        status_data = get_status()
        if status_data:
            output(status_data, ctx.obj['output_format'])


@tune.command()
@click.argument("tuning_id")
@click.pass_context
def results(ctx, tuning_id: str):
    """Get auto-tuning results and best parameters"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/tune/sessions/{tuning_id}/results",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                results = response.json()
                output(results, ctx.obj['output_format'])
            else:
                error(f"Failed to get tuning results: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@optimize.command()
@click.argument("agent_id")
@click.pass_context
def disable(ctx, agent_id: str):
    """Disable autonomous optimization for agent"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/optimize/agents/{agent_id}/disable",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Autonomous optimization disabled for agent {agent_id}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to disable optimization: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)
