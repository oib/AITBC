"""Governance commands for AITBC CLI"""

import click
import httpx
import json
import os
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
from ..utils import output, error, success


GOVERNANCE_DIR = Path.home() / ".aitbc" / "governance"


def _ensure_governance_dir():
    GOVERNANCE_DIR.mkdir(parents=True, exist_ok=True)
    proposals_file = GOVERNANCE_DIR / "proposals.json"
    if not proposals_file.exists():
        with open(proposals_file, "w") as f:
            json.dump({"proposals": []}, f, indent=2)
    return proposals_file


def _load_proposals():
    proposals_file = _ensure_governance_dir()
    with open(proposals_file) as f:
        return json.load(f)


def _save_proposals(data):
    proposals_file = _ensure_governance_dir()
    with open(proposals_file, "w") as f:
        json.dump(data, f, indent=2)


@click.group()
def governance():
    """Governance proposals and voting"""
    pass


@governance.command()
@click.argument("title")
@click.option("--description", required=True, help="Proposal description")
@click.option("--type", "proposal_type", type=click.Choice(["parameter_change", "feature_toggle", "funding", "general"]), default="general", help="Proposal type")
@click.option("--parameter", help="Parameter to change (for parameter_change type)")
@click.option("--value", help="New value (for parameter_change type)")
@click.option("--amount", type=float, help="Funding amount (for funding type)")
@click.option("--duration", type=int, default=7, help="Voting duration in days")
@click.pass_context
def propose(ctx, title: str, description: str, proposal_type: str,
            parameter: Optional[str], value: Optional[str],
            amount: Optional[float], duration: int):
    """Create a governance proposal"""
    import secrets

    data = _load_proposals()
    proposal_id = f"prop_{secrets.token_hex(6)}"
    now = datetime.now()

    proposal = {
        "id": proposal_id,
        "title": title,
        "description": description,
        "type": proposal_type,
        "proposer": os.environ.get("USER", "unknown"),
        "created_at": now.isoformat(),
        "voting_ends": (now + timedelta(days=duration)).isoformat(),
        "duration_days": duration,
        "status": "active",
        "votes": {"for": 0, "against": 0, "abstain": 0},
        "voters": [],
    }

    if proposal_type == "parameter_change":
        proposal["parameter"] = parameter
        proposal["new_value"] = value
    elif proposal_type == "funding":
        proposal["amount"] = amount

    data["proposals"].append(proposal)
    _save_proposals(data)

    success(f"Proposal '{title}' created: {proposal_id}")
    output({
        "proposal_id": proposal_id,
        "title": title,
        "type": proposal_type,
        "status": "active",
        "voting_ends": proposal["voting_ends"],
        "duration_days": duration
    }, ctx.obj.get('output_format', 'table'))


@governance.command()
@click.argument("proposal_id")
@click.argument("choice", type=click.Choice(["for", "against", "abstain"]))
@click.option("--voter", default=None, help="Voter identity (defaults to $USER)")
@click.option("--weight", type=float, default=1.0, help="Vote weight")
@click.pass_context
def vote(ctx, proposal_id: str, choice: str, voter: Optional[str], weight: float):
    """Cast a vote on a proposal"""
    data = _load_proposals()
    voter = voter or os.environ.get("USER", "unknown")

    proposal = next((p for p in data["proposals"] if p["id"] == proposal_id), None)
    if not proposal:
        error(f"Proposal '{proposal_id}' not found")
        ctx.exit(1)
        return

    if proposal["status"] != "active":
        error(f"Proposal is '{proposal['status']}', not active")
        ctx.exit(1)
        return

    # Check if voting period has ended
    voting_ends = datetime.fromisoformat(proposal["voting_ends"])
    if datetime.now() > voting_ends:
        proposal["status"] = "closed"
        _save_proposals(data)
        error("Voting period has ended")
        ctx.exit(1)
        return

    # Check if already voted
    if voter in proposal["voters"]:
        error(f"'{voter}' has already voted on this proposal")
        ctx.exit(1)
        return

    proposal["votes"][choice] += weight
    proposal["voters"].append(voter)
    _save_proposals(data)

    total_votes = sum(proposal["votes"].values())
    success(f"Vote recorded: {choice} (weight: {weight})")
    output({
        "proposal_id": proposal_id,
        "voter": voter,
        "choice": choice,
        "weight": weight,
        "current_tally": proposal["votes"],
        "total_votes": total_votes
    }, ctx.obj.get('output_format', 'table'))


@governance.command(name="list")
@click.option("--status", type=click.Choice(["active", "closed", "approved", "rejected", "all"]), default="all", help="Filter by status")
@click.option("--type", "proposal_type", help="Filter by proposal type")
@click.option("--limit", type=int, default=20, help="Max proposals to show")
@click.pass_context
def list_proposals(ctx, status: str, proposal_type: Optional[str], limit: int):
    """List governance proposals"""
    data = _load_proposals()
    proposals = data["proposals"]

    # Auto-close expired proposals
    now = datetime.now()
    for p in proposals:
        if p["status"] == "active":
            voting_ends = datetime.fromisoformat(p["voting_ends"])
            if now > voting_ends:
                total = sum(p["votes"].values())
                if total > 0 and p["votes"]["for"] > p["votes"]["against"]:
                    p["status"] = "approved"
                else:
                    p["status"] = "rejected"
    _save_proposals(data)

    # Filter
    if status != "all":
        proposals = [p for p in proposals if p["status"] == status]
    if proposal_type:
        proposals = [p for p in proposals if p["type"] == proposal_type]

    proposals = proposals[-limit:]

    if not proposals:
        output({"message": "No proposals found", "filter": status}, ctx.obj.get('output_format', 'table'))
        return

    summary = [{
        "id": p["id"],
        "title": p["title"],
        "type": p["type"],
        "status": p["status"],
        "votes_for": p["votes"]["for"],
        "votes_against": p["votes"]["against"],
        "votes_abstain": p["votes"]["abstain"],
        "created_at": p["created_at"]
    } for p in proposals]

    output(summary, ctx.obj.get('output_format', 'table'))


@governance.command()
@click.argument("proposal_id")
@click.pass_context
def result(ctx, proposal_id: str):
    """Show voting results for a proposal"""
    data = _load_proposals()

    proposal = next((p for p in data["proposals"] if p["id"] == proposal_id), None)
    if not proposal:
        error(f"Proposal '{proposal_id}' not found")
        ctx.exit(1)
        return

    # Auto-close if expired
    now = datetime.now()
    if proposal["status"] == "active":
        voting_ends = datetime.fromisoformat(proposal["voting_ends"])
        if now > voting_ends:
            total = sum(proposal["votes"].values())
            if total > 0 and proposal["votes"]["for"] > proposal["votes"]["against"]:
                proposal["status"] = "approved"
            else:
                proposal["status"] = "rejected"
            _save_proposals(data)

    votes = proposal["votes"]
    total = sum(votes.values())
    pct_for = (votes["for"] / total * 100) if total > 0 else 0
    pct_against = (votes["against"] / total * 100) if total > 0 else 0

    result_data = {
        "proposal_id": proposal["id"],
        "title": proposal["title"],
        "type": proposal["type"],
        "status": proposal["status"],
        "proposer": proposal["proposer"],
        "created_at": proposal["created_at"],
        "voting_ends": proposal["voting_ends"],
        "votes_for": votes["for"],
        "votes_against": votes["against"],
        "votes_abstain": votes["abstain"],
        "total_votes": total,
        "pct_for": round(pct_for, 1),
        "pct_against": round(pct_against, 1),
        "voter_count": len(proposal["voters"]),
        "outcome": proposal["status"]
    }

    if proposal.get("parameter"):
        result_data["parameter"] = proposal["parameter"]
        result_data["new_value"] = proposal.get("new_value")
    if proposal.get("amount"):
        result_data["amount"] = proposal["amount"]

    output(result_data, ctx.obj.get('output_format', 'table'))
