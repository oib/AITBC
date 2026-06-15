"""Workflow command handlers for AITBC CLI."""

import json
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

COORDINATOR_URL = "http://localhost:8203"
CLIENT_API_KEY = "aitbc-client-key-secure-token-production"


def handle_workflow_create(args, render_mapping):
    """Handle workflow create command - creates an AI job as a workflow."""
    name = getattr(args, "name", None) or "unnamed-workflow"
    template = getattr(args, "template", "custom")
    model = getattr(args, "model", "llama2:7b")
    prompt = getattr(args, "prompt", "Hello")

    # Create a job through the coordinator API
    job_data = {
        "payload": {"type": "inference", "model": model, "prompt": prompt},
        "constraints": {"max_price": 0.1, "region": "localhost"},
        "ttl_seconds": 900,
    }

    headers = {"X-Api-Key": CLIENT_API_KEY, "Content-Type": "application/json"}

    try:
        response = requests.post(f"{COORDINATOR_URL}/v1/jobs", json=job_data, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()

        workflow_data = {
            "workflow_id": result.get("job_id"),
            "name": name,
            "template": template,
            "status": "created",
            "model": model,
            "estimated_duration": "1-2 minutes",
        }

        logger.info("Workflow created: %s", workflow_data["workflow_id"])
        render_mapping("Workflow:", workflow_data)
    except Exception as e:
        logger.error("Failed to create workflow: %s", e)
        render_mapping("Error:", {"message": str(e)})


def handle_workflow_schedule(args, render_mapping):
    """Handle workflow schedule command - schedules recurring AI jobs."""
    name = getattr(args, "name", None)
    cron = getattr(args, "cron", None)
    command = getattr(args, "command", None)

    # For now, return scheduling info (actual scheduling would require a scheduler service)
    schedule_data = {
        "schedule_id": f"schedule_{int(datetime.now().timestamp())}",
        "workflow_name": name,
        "cron_expression": cron,
        "command": command,
        "status": "scheduled",
        "next_run": "pending",
        "note": "Scheduler service integration required for actual execution",
    }

    logger.info("Workflow scheduled: %s", schedule_data["schedule_id"])
    render_mapping("Schedule:", schedule_data)


def handle_workflow_monitor(args, output_format, render_mapping):
    """Handle workflow monitor command - monitors job status through coordinator."""
    _ = getattr(args, "name", None)

    headers = {"X-Api-Key": CLIENT_API_KEY, "Content-Type": "application/json"}

    try:
        response = requests.get(f"{COORDINATOR_URL}/v1/jobs", headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()

        jobs = result.get("items", [])
        running = sum(1 for j in jobs if j.get("state") == "RUNNING")
        completed = sum(1 for j in jobs if j.get("state") == "COMPLETED")
        failed = sum(1 for j in jobs if j.get("state") == "FAILED")

        monitor_data = {
            "status": "active",
            "workflows_running": running,
            "workflows_completed": completed,
            "workflows_failed": failed,
            "total_jobs": len(jobs),
            "last_check": datetime.now().isoformat(),
        }

        if output_format(args) == "json":
            logger.info(json.dumps(monitor_data, indent=2))
        else:
            render_mapping("Workflow Monitor:", monitor_data)
    except Exception as e:
        logger.error("Failed to monitor workflows: %s", e)
        monitor_data = {"status": "error", "message": str(e), "last_check": datetime.now().isoformat()}
        render_mapping("Workflow Monitor:", monitor_data)
