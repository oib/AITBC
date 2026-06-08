"""
Hermes training commands for AITBC CLI
"""

import datetime
import json
import os
import subprocess
import time

import click

from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

from ..config import get_config
from ..utils import error, output, success

logger = get_logger(__name__)


@click.group()
def hermes():
    """Hermes training operations commands"""
    pass


@hermes.command()
@click.option('--agent-id', required=True, help='Agent ID')
@click.option('--training-type', required=True, help='Type of training')
@click.option('--dataset', help='Dataset to use')
@click.option('--epochs', type=int, default=100, help='Number of training epochs')
@click.option('--batch-size', type=int, default=32, help='Batch size')
@click.option('--training-data', help='Path to training data JSON file')
@click.option('--stage', help='Training stage')
def train(agent_id: str, training_type: str, dataset: str | None, epochs: int, batch_size: int, training_data: str | None, stage: str | None):
    """Start Hermes training for an agent"""
    if training_data:
        if not os.path.exists(training_data):
            error(f"Training data file not found: {training_data}")
            return

        try:
            with open(training_data) as f:
                training_config = json.load(f)

            # Validate training data matches stage
            if stage and training_config.get('stage') != stage:
                error(f"Training data stage mismatch: expected {stage}, got {training_config.get('stage')}")
                return

            # Initialize logging
            log_dir = "/var/log/aitbc/agent-training"
            os.makedirs(log_dir, exist_ok=True)
            log_file = f"{log_dir}/agent_{agent_id}_{stage}_{int(time.time())}.log"

            # Execute training operations
            operations = training_config.get('training_data', {}).get('operations', [])
            completed_ops = 0
            failed_ops = 0

            success(f"Starting training for agent {agent_id}")
            success(f"Operations to execute: {len(operations)}")

            for i, op in enumerate(operations, 1):
                operation = op.get('operation')
                parameters = op.get('parameters', {})

                log_entry = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "agent_id": agent_id,
                    "stage": stage,
                    "operation": operation,
                    "prompt": {
                        "parameters": parameters,
                        "expected_result": op.get('expected_result')
                    }
                }

                # Execute training via hermes agent
                start_time = time.time()
                try:
                    prompt_message = f"Execute AITBC CLI command: {operation}"
                    if parameters:
                        prompt_message += f" with parameters: {json.dumps(parameters)}"

                    cmd = ["hermes", "agent", "--message", prompt_message, "--agent", "main"]

                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                    duration_ms = int((time.time() - start_time) * 1000)

                    if result.returncode == 0:
                        reply = {
                            "status": "completed",
                            "result": result.stdout.strip() if result.stdout else "Command executed successfully",
                            "cli_output": result.stdout.strip()
                        }
                        log_entry["status"] = "completed"
                        completed_ops += 1
                        success(f"Operation {i}/{len(operations)}: {operation} - completed ({duration_ms}ms)")
                    else:
                        reply = {
                            "status": "error",
                            "error": result.stderr.strip() if result.stderr else "Command failed",
                            "cli_output": result.stdout.strip(),
                            "cli_error": result.stderr.strip()
                        }
                        log_entry["status"] = "failed"
                        failed_ops += 1
                        error(f"Operation {i}/{len(operations)}: {operation} - failed")

                    log_entry["reply"] = reply
                    log_entry["duration_ms"] = duration_ms

                    # Write log entry
                    with open(log_file, 'a') as f:
                        f.write(json.dumps(log_entry) + "\n")

                except subprocess.TimeoutExpired:
                    duration_ms = int((time.time() - start_time) * 1000)
                    reply = {
                        "status": "error",
                        "error": "Command timed out after 30 seconds"
                    }
                    log_entry["status"] = "failed"
                    log_entry["reply"] = reply
                    log_entry["duration_ms"] = duration_ms
                    failed_ops += 1
                    error(f"Operation {i}/{len(operations)}: {operation} - timed out")

                    with open(log_file, 'a') as f:
                        f.write(json.dumps(log_entry) + "\n")
                except Exception as e:
                    error(f"Operation {i}/{len(operations)}: {operation} - exception: {e}")
                    failed_ops += 1

            success(f"Training completed: {completed_ops}/{len(operations)} successful")
            success(f"Log file: {log_file}")

        except Exception as e:
            error(f"Error loading training data: {e}")
    else:
        success(f"Start {training_type} training for agent {agent_id}")
        success(f"Epochs: {epochs}, Batch size: {batch_size}")


@hermes.command()
@click.option('--agent-id', help='Agent ID')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
def status(agent_id: str | None, format: str):
    """Get Hermes training status"""
    success(f"Get Hermes training status for agent {agent_id}")
    # TODO: Implement actual status check from coordinator API


@hermes.command()
@click.option('--agent-id', help='Agent ID')
def stop(agent_id: str | None):
    """Stop Hermes training"""
    success(f"Stop Hermes training for agent {agent_id}")
    # TODO: Implement actual stop command via coordinator API


@hermes.command()
@click.argument('message')
@click.option('--to-agent', help='Target agent ID')
@click.option('--priority', default='normal', help='Message priority')
@click.pass_context
def send(ctx, message: str, to_agent: str | None, priority: str):
    """Send a message via hermes service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.hermes_service_url, timeout=10)
        message_data = {
            "message": message,
            "priority": priority
        }
        if to_agent:
            message_data["to_agent"] = to_agent

        result = http_client.post("/hermes/send", json=message_data)
        success("Message sent via hermes")
        output(result, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error sending message: {e}")


@hermes.command()
@click.option('--limit', type=int, default=20, help='Number of messages to return')
@click.pass_context
def receive(ctx, limit: int):
    """Receive messages from hermes service"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.hermes_service_url, timeout=10)
        messages_data = http_client.get("/hermes/messages", params={"limit": limit})
        success("Messages:")
        output(messages_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error receiving messages: {e}")


@hermes.command()
@click.pass_context
def peers(ctx):
    """List hermes service peers"""
    config = get_config()

    try:
        http_client = AITBCHTTPClient(base_url=config.hermes_service_url, timeout=10)
        peers_data = http_client.get("/hermes/peers")
        success("Hermes Peers:")
        output(peers_data, ctx.obj.get("output_format", "table"))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error fetching peers: {e}")

