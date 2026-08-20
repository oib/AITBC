"""Compliance classification and audit CLI commands (v0.15.2 §B3)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import click

from aitbc.compliance.policies import ComplianceFramework, DataClassification, load_policy_template, normalize_classification

from ..config import get_config
from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


def _api_client() -> AITBCHTTPClient | None:
    """Return a client for the coordinator API if a URL is configured."""
    config = get_config()
    url = config.coordinator_api_url or os.getenv("COORDINATOR_API_URL", "")
    if not url:
        return None
    return AITBCHTTPClient(base_url=url, timeout=config.timeout, api_key=config.api_key or "")


@click.group()
def compliance():
    """Compliance policy, classification, and audit commands."""
    pass


@compliance.command()
@click.option("--framework", default="hipaa", help="Compliance framework to check against")
@click.option("--classification", default="phi", help="Data classification label")
@click.pass_context
def check(ctx, framework: str, classification: str):
    """Check whether a classification is allowed by a policy."""
    try:
        policy = load_policy_template(ComplianceFramework(framework))
        label = normalize_classification(classification)
        allowed = policy.allows_classification(label)
        result = {
            "framework": framework,
            "classification": classification,
            "allowed": allowed,
            "policy_id": policy.policy_id,
            "status": "simulated",
        }
        output(result, ctx.obj.get("output_format", "table"), title="Compliance Check")
    except Exception as e:
        abort(ctx, f"Error checking compliance: {e}", from_exception=e)


@compliance.command()
@click.argument("label")
@click.pass_context
def classify(ctx, label: str):
    """Normalize a data classification label."""
    try:
        normalized = normalize_classification(label)
        result = {
            "input": label,
            "normalized": normalized.value,
            "sensitive": normalized
            in {
                DataClassification.PHI,
                DataClassification.PII,
                DataClassification.PCI,
                DataClassification.CONFIDENTIAL,
                DataClassification.RESTRICTED,
            },
        }
        output(result, ctx.obj.get("output_format", "table"), title="Classification")
    except Exception as e:
        abort(ctx, f"Error normalizing classification {label}: {e}", from_exception=e)


@compliance.command("export-audit")
@click.option("--output-file", default="audit-export.json", help="File to write exported audit records")
@click.pass_context
def export_audit(ctx, output_file: str):
    """Export a simulated compliance audit trail to a JSON file."""
    try:
        client = _api_client()
        records: list[dict[str, Any]] | dict[str, Any]
        if client is None:
            records = [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "subject_id": "patient-1",
                    "actor_id": "doctor-1",
                    "action": "access",
                    "resource_id": "phi-record-1",
                    "outcome": "allowed",
                },
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "subject_id": "merchant-1",
                    "actor_id": "processor-1",
                    "action": "authorize",
                    "resource_id": "txn-1",
                    "outcome": "approved",
                },
            ]
        else:
            records = client.get("/v1/compliance/audit-logs")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({"exported_at": datetime.now(UTC).isoformat(), "records": records}, f, indent=2)
        result = {
            "output_file": output_file,
            "record_count": len(records),
            "status": "simulated" if client is None else "exported",
        }
        output(result, ctx.obj.get("output_format", "table"), title="Audit Export")
    except NetworkError as e:
        abort(ctx, f"Coordinator API error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error exporting audit records: {e}", from_exception=e)
