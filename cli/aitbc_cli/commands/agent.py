"""Agent commands for AITBC CLI - Advanced AI Agent Management"""

import click
import httpx
import json
import time
import uuid
from typing import Optional, Dict, Any, List
from pathlib import Path
from ..utils import output, error, success, warning


@click.group()
def agent():
    """Advanced AI agent workflow and execution management"""
    pass


@agent.command()
@click.option("--name", required=True, help="Agent workflow name")
@click.option("--description", default="", help="Agent description")
@click.option("--workflow-file", type=click.File('r'), help="Workflow definition from JSON file")
@click.option("--verification", default="basic", type=click.Choice(["basic", "full", "zero-knowledge"]),
              help="Verification level for agent execution")
@click.option("--max-execution-time", default=3600, help="Maximum execution time in seconds")
@click.option("--max-cost-budget", default=0.0, help="Maximum cost budget")
@click.pass_context
def create(ctx, name: str, description: str, workflow_file, verification: str, 
          max_execution_time: int, max_cost_budget: float):
    """Create a new AI agent workflow"""
    config = ctx.obj['config']
    
    # Build workflow data
    workflow_data = {
        "name": name,
        "description": description,
        "verification_level": verification,
        "max_execution_time": max_execution_time,
        "max_cost_budget": max_cost_budget
    }
    
    if workflow_file:
        try:
            workflow_spec = json.load(workflow_file)
            workflow_data.update(workflow_spec)
        except Exception as e:
            error(f"Failed to read workflow file: {e}")
            return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/agents/workflows",
                headers={"X-Api-Key": config.api_key or ""},
                json=workflow_data
            )
            
            if response.status_code == 201:
                workflow = response.json()
                success(f"Agent workflow created: {workflow['id']}")
                output(workflow, ctx.obj['output_format'])
            else:
                error(f"Failed to create agent workflow: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@agent.command()
@click.option("--type", "agent_type", help="Filter by agent type")
@click.option("--status", help="Filter by status")
@click.option("--verification", help="Filter by verification level")
@click.option("--limit", default=20, help="Number of agents to list")
@click.option("--owner", help="Filter by owner ID")
@click.pass_context
def list(ctx, agent_type: Optional[str], status: Optional[str], 
         verification: Optional[str], limit: int, owner: Optional[str]):
    """List available AI agent workflows"""
    config = ctx.obj['config']
    
    params = {"limit": limit}
    if agent_type:
        params["type"] = agent_type
    if status:
        params["status"] = status
    if verification:
        params["verification"] = verification
    if owner:
        params["owner"] = owner
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/agents/workflows",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                workflows = response.json()
                output(workflows, ctx.obj['output_format'])
            else:
                error(f"Failed to list agent workflows: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@agent.command()
@click.argument("agent_id")
@click.option("--inputs", type=click.File('r'), help="Input data from JSON file")
@click.option("--verification", default="basic", type=click.Choice(["basic", "full", "zero-knowledge"]),
              help="Verification level for this execution")
@click.option("--priority", default="normal", type=click.Choice(["low", "normal", "high"]),
              help="Execution priority")
@click.option("--timeout", default=3600, help="Execution timeout in seconds")
@click.pass_context
def execute(ctx, agent_id: str, inputs, verification: str, priority: str, timeout: int):
    """Execute an AI agent workflow"""
    config = ctx.obj['config']
    
    # Prepare execution data
    execution_data = {
        "verification_level": verification,
        "priority": priority,
        "timeout_seconds": timeout
    }
    
    if inputs:
        try:
            input_data = json.load(inputs)
            execution_data["inputs"] = input_data
        except Exception as e:
            error(f"Failed to read inputs file: {e}")
            return
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/agents/{agent_id}/execute",
                headers={"X-Api-Key": config.api_key or ""},
                json=execution_data
            )
            
            if response.status_code == 202:
                execution = response.json()
                success(f"Agent execution started: {execution['id']}")
                output(execution, ctx.obj['output_format'])
            else:
                error(f"Failed to start agent execution: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@agent.command()
@click.argument("execution_id")
@click.option("--watch", is_flag=True, help="Watch execution status in real-time")
@click.option("--interval", default=5, help="Watch interval in seconds")
@click.pass_context
def status(ctx, execution_id: str, watch: bool, interval: int):
    """Get status of agent execution"""
    config = ctx.obj['config']
    
    def get_status():
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{config.coordinator_url}/v1/agents/executions/{execution_id}",
                    headers={"X-Api-Key": config.api_key or ""}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    error(f"Failed to get execution status: {response.status_code}")
                    return None
        except Exception as e:
            error(f"Network error: {e}")
            return None
    
    if watch:
        click.echo(f"Watching execution {execution_id} (Ctrl+C to stop)...")
        while True:
            status_data = get_status()
            if status_data:
                click.clear()
                click.echo(f"Execution Status: {status_data.get('status', 'Unknown')}")
                click.echo(f"Progress: {status_data.get('progress', 0)}%")
                click.echo(f"Current Step: {status_data.get('current_step', 'N/A')}")
                click.echo(f"Cost: ${status_data.get('total_cost', 0.0):.4f}")
                
                if status_data.get('status') in ['completed', 'failed']:
                    break
            
            time.sleep(interval)
    else:
        status_data = get_status()
        if status_data:
            output(status_data, ctx.obj['output_format'])


@agent.command()
@click.argument("execution_id")
@click.option("--verify", is_flag=True, help="Verify cryptographic receipt")
@click.option("--download", type=click.Path(), help="Download receipt to file")
@click.pass_context
def receipt(ctx, execution_id: str, verify: bool, download: Optional[str]):
    """Get verifiable receipt for completed execution"""
    config = ctx.obj['config']
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/agents/executions/{execution_id}/receipt",
                headers={"X-Api-Key": config.api_key or ""}
            )
            
            if response.status_code == 200:
                receipt_data = response.json()
                
                if verify:
                    # Verify receipt
                    verify_response = client.post(
                        f"{config.coordinator_url}/v1/agents/receipts/verify",
                        headers={"X-Api-Key": config.api_key or ""},
                        json={"receipt": receipt_data}
                    )
                    
                    if verify_response.status_code == 200:
                        verification_result = verify_response.json()
                        receipt_data["verification"] = verification_result
                        
                        if verification_result.get("valid"):
                            success("Receipt verification: PASSED")
                        else:
                            warning("Receipt verification: FAILED")
                    else:
                        warning("Could not verify receipt")
                
                if download:
                    with open(download, 'w') as f:
                        json.dump(receipt_data, f, indent=2)
                    success(f"Receipt downloaded to {download}")
                else:
                    output(receipt_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get execution receipt: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def network():
    """Multi-agent collaborative network management"""
    pass


agent.add_command(network)


@network.command()
@click.option("--name", required=True, help="Network name")
@click.option("--agents", required=True, help="Comma-separated list of agent IDs")
@click.option("--description", default="", help="Network description")
@click.option("--coordination", default="centralized", 
              type=click.Choice(["centralized", "decentralized", "hybrid"]),
              help="Coordination strategy")
@click.pass_context
def create(ctx, name: str, agents: str, description: str, coordination: str):
    """Create collaborative agent network"""
    config = ctx.obj['config']
    
    agent_ids = [agent_id.strip() for agent_id in agents.split(',')]
    
    network_data = {
        "name": name,
        "description": description,
        "agents": agent_ids,
        "coordination_strategy": coordination
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/agents/networks",
                headers={"X-Api-Key": config.api_key or ""},
                json=network_data
            )
            
            if response.status_code == 201:
                network = response.json()
                success(f"Agent network created: {network['id']}")
                output(network, ctx.obj['output_format'])
            else:
                error(f"Failed to create agent network: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@network.command()
@click.argument("network_id")
@click.option("--task", type=click.File('r'), required=True, help="Task definition JSON file")
@click.option("--priority", default="normal", type=click.Choice(["low", "normal", "high"]),
              help="Execution priority")
@click.pass_context
def execute(ctx, network_id: str, task, priority: str):
    """Execute collaborative task on agent network"""
    config = ctx.obj['config']
    
    try:
        task_data = json.load(task)
    except Exception as e:
        error(f"Failed to read task file: {e}")
        return
    
    execution_data = {
        "task": task_data,
        "priority": priority
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/agents/networks/{network_id}/execute",
                headers={"X-Api-Key": config.api_key or ""},
                json=execution_data
            )
            
            if response.status_code == 202:
                execution = response.json()
                success(f"Network execution started: {execution['id']}")
                output(execution, ctx.obj['output_format'])
            else:
                error(f"Failed to start network execution: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@network.command()
@click.argument("network_id")
@click.option("--metrics", default="all", help="Comma-separated metrics to show")
@click.option("--real-time", is_flag=True, help="Show real-time metrics")
@click.pass_context
def status(ctx, network_id: str, metrics: str, real_time: bool):
    """Get agent network status and performance metrics"""
    config = ctx.obj['config']
    
    params = {}
    if metrics != "all":
        params["metrics"] = metrics
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/agents/networks/{network_id}/status",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                status_data = response.json()
                output(status_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get network status: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@network.command()
@click.argument("network_id")
@click.option("--objective", default="efficiency", 
              type=click.Choice(["speed", "efficiency", "cost", "quality"]),
              help="Optimization objective")
@click.pass_context
def optimize(ctx, network_id: str, objective: str):
    """Optimize agent network collaboration"""
    config = ctx.obj['config']
    
    optimization_data = {"objective": objective}
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/agents/networks/{network_id}/optimize",
                headers={"X-Api-Key": config.api_key or ""},
                json=optimization_data
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Network optimization completed")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to optimize network: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.group()
def learning():
    """Agent adaptive learning and training management"""
    pass


agent.add_command(learning)


@learning.command()
@click.argument("agent_id")
@click.option("--mode", default="reinforcement", 
              type=click.Choice(["reinforcement", "transfer", "meta"]),
              help="Learning mode")
@click.option("--feedback-source", help="Feedback data source")
@click.option("--learning-rate", default=0.001, help="Learning rate")
@click.pass_context
def enable(ctx, agent_id: str, mode: str, feedback_source: Optional[str], learning_rate: float):
    """Enable adaptive learning for agent"""
    config = ctx.obj['config']
    
    learning_config = {
        "mode": mode,
        "learning_rate": learning_rate
    }
    
    if feedback_source:
        learning_config["feedback_source"] = feedback_source
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/agents/{agent_id}/learning/enable",
                headers={"X-Api-Key": config.api_key or ""},
                json=learning_config
            )
            
            if response.status_code == 200:
                result = response.json()
                success(f"Adaptive learning enabled for agent {agent_id}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to enable learning: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@learning.command()
@click.argument("agent_id")
@click.option("--feedback", type=click.File('r'), required=True, help="Feedback data JSON file")
@click.option("--epochs", default=10, help="Number of training epochs")
@click.pass_context
def train(ctx, agent_id: str, feedback, epochs: int):
    """Train agent with feedback data"""
    config = ctx.obj['config']
    
    try:
        feedback_data = json.load(feedback)
    except Exception as e:
        error(f"Failed to read feedback file: {e}")
        return
    
    training_data = {
        "feedback": feedback_data,
        "epochs": epochs
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/agents/{agent_id}/learning/train",
                headers={"X-Api-Key": config.api_key or ""},
                json=training_data
            )
            
            if response.status_code == 202:
                training = response.json()
                success(f"Training started: {training['id']}")
                output(training, ctx.obj['output_format'])
            else:
                error(f"Failed to start training: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@learning.command()
@click.argument("agent_id")
@click.option("--metrics", default="accuracy,efficiency", help="Comma-separated metrics to show")
@click.pass_context
def progress(ctx, agent_id: str, metrics: str):
    """Review agent learning progress"""
    config = ctx.obj['config']
    
    params = {"metrics": metrics}
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/agents/{agent_id}/learning/progress",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                progress_data = response.json()
                output(progress_data, ctx.obj['output_format'])
            else:
                error(f"Failed to get learning progress: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@learning.command()
@click.argument("agent_id")
@click.option("--format", default="onnx", type=click.Choice(["onnx", "pickle", "torch"]),
              help="Export format")
@click.option("--output-path", type=click.Path(), help="Output file path")
@click.pass_context
def export(ctx, agent_id: str, format: str, output_path: Optional[str]):
    """Export learned agent model"""
    config = ctx.obj['config']
    
    params = {"format": format}
    
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{config.coordinator_url}/v1/agents/{agent_id}/learning/export",
                headers={"X-Api-Key": config.api_key or ""},
                params=params
            )
            
            if response.status_code == 200:
                if output_path:
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    success(f"Model exported to {output_path}")
                else:
                    # Output metadata about the export
                    export_info = response.headers.get('X-Export-Info', '{}')
                    try:
                        info_data = json.loads(export_info)
                        output(info_data, ctx.obj['output_format'])
                    except:
                        output({"status": "export_ready", "format": format}, ctx.obj['output_format'])
            else:
                error(f"Failed to export model: {response.status_code}")
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


@click.command()
@click.option("--type", required=True, 
              type=click.Choice(["optimization", "feature", "bugfix", "documentation"]),
              help="Contribution type")
@click.option("--description", required=True, help="Contribution description")
@click.option("--github-repo", default="oib/AITBC", help="GitHub repository")
@click.option("--branch", default="main", help="Target branch")
@click.pass_context
def submit_contribution(ctx, type: str, description: str, github_repo: str, branch: str):
    """Submit contribution to platform via GitHub"""
    config = ctx.obj['config']
    
    contribution_data = {
        "type": type,
        "description": description,
        "github_repo": github_repo,
        "target_branch": branch
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{config.coordinator_url}/v1/agents/contributions",
                headers={"X-Api-Key": config.api_key or ""},
                json=contribution_data
            )
            
            if response.status_code == 201:
                result = response.json()
                success(f"Contribution submitted: {result['id']}")
                output(result, ctx.obj['output_format'])
            else:
                error(f"Failed to submit contribution: {response.status_code}")
                if response.text:
                    error(response.text)
                ctx.exit(1)
    except Exception as e:
        error(f"Network error: {e}")
        ctx.exit(1)


agent.add_command(submit_contribution)
