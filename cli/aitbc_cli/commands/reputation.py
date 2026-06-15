"""
Reputation Management CLI Commands
Provides CLI commands for managing agent reputation, trust scores, and community feedback
"""

import click

from ..utils.http_client import get_logger

logger = get_logger(__name__)


@click.group(name="reputation")
def reputation():
    """Reputation management commands"""
    pass


@reputation.command("profile")
@click.argument("agent_id")
@click.option("--format", "json", help="Output format (json, table)")
def get_profile(agent_id: str, format: str):
    """Get reputation profile for an agent"""
    import json
    from pathlib import Path

    import requests

    try:
        # Try to get coordinator API URL from config
        config_path = Path.home() / ".aitbc" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_url = config.get("coordinator_api_url", "http://localhost:8203")
        else:
            api_url = "http://localhost:8203"

        response = requests.get(f"{api_url}/reputation/profile/{agent_id}", timeout=10)

        if response.status_code == 200:
            data = response.json()
            if format == "json":
                click.echo(json.dumps(data, indent=2))
            else:
                click.echo(f"Agent ID: {data['agent_id']}")
                click.echo(f"Trust Score: {data['trust_score']:.2f}/1000")
                click.echo(f"Reputation Level: {data['reputation_level']}")
                click.echo(f"Performance Rating: {data['performance_rating']}/5.0")
                click.echo(f"Reliability Score: {data['reliability_score']:.2f}%")
                click.echo(f"Community Rating: {data['community_rating']}/5.0")
                click.echo(f"Total Earnings: {data['total_earnings']:.4f} AITBC")
                click.echo(f"Transaction Count: {data['transaction_count']}")
                click.echo(f"Success Rate: {data['success_rate']:.2f}%")
                click.echo(f"Jobs Completed: {data['jobs_completed']}")
                click.echo(f"Jobs Failed: {data['jobs_failed']}")
        else:
            click.echo(f"Error: {response.status_code} - {response.text}", err=True)
    except Exception as e:
        logger.error("Error getting reputation profile: %s", e)
        click.echo(f"Error: {str(e)}", err=True)


@reputation.command("feedback")
@click.argument("agent_id")
@click.argument("reviewer_id")
@click.option("--overall", type=float, default=3.0, help="Overall rating (1-5)")
@click.option("--performance", type=float, default=3.0, help="Performance rating (1-5)")
@click.option("--communication", type=float, default=3.0, help="Communication rating (1-5)")
@click.option("--reliability", type=float, default=3.0, help="Reliability rating (1-5)")
@click.option("--value", type=float, default=3.0, help="Value rating (1-5)")
@click.option("--text", default="", help="Feedback text")
@click.option("--tag", multiple=True, help="Feedback tags")
def add_feedback(
    agent_id: str,
    reviewer_id: str,
    overall: float,
    performance: float,
    communication: float,
    reliability: float,
    value: float,
    text: str,
    tag: tuple,
):
    """Add community feedback for an agent"""
    import json
    from pathlib import Path

    import requests

    try:
        # Try to get coordinator API URL from config
        config_path = Path.home() / ".aitbc" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_url = config.get("coordinator_api_url", "http://localhost:8203")
        else:
            api_url = "http://localhost:8203"

        ratings = {
            "overall": overall,
            "performance": performance,
            "communication": communication,
            "reliability": reliability,
            "value": value,
        }

        payload = {"reviewer_id": reviewer_id, "ratings": ratings, "feedback_text": text, "tags": list(tag)}

        response = requests.post(f"{api_url}/reputation/feedback/{agent_id}", json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            click.echo("Feedback added successfully!")
            click.echo(f"Feedback ID: {data['id']}")
            click.echo(f"Overall Rating: {data['overall_rating']}/5.0")
            click.echo(f"Moderation Status: {data['moderation_status']}")
        else:
            click.echo(f"Error: {response.status_code} - {response.text}", err=True)
    except Exception as e:
        logger.error("Error adding feedback: %s", e)
        click.echo(f"Error: {str(e)}", err=True)


@reputation.command("leaderboard")
@click.option("--category", default="trust_score", help="Category to rank by")
@click.option("--limit", default=10, help="Number of results")
@click.option("--region", help="Filter by region")
@click.option("--format", default="json", help="Output format (json, table)")
def leaderboard(category: str, limit: int, region: str, format: str):
    """Get reputation leaderboard"""
    import json
    from pathlib import Path

    import requests

    try:
        # Try to get coordinator API URL from config
        config_path = Path.home() / ".aitbc" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_url = config.get("coordinator_api_url", "http://localhost:8203")
        else:
            api_url = "http://localhost:8203"

        params = {"category": category, "limit": limit}
        if region:
            params["region"] = region

        response = requests.get(f"{api_url}/reputation/leaderboard", params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if format == "json":
                click.echo(json.dumps(data, indent=2))
            else:
                click.echo(f"{'Rank':<6} {'Agent ID':<20} {'Trust Score':<12} {'Level':<12} {'Transactions':<12}")
                click.echo("-" * 72)
                for entry in data:
                    click.echo(
                        f"{entry['rank']:<6} {entry['agent_id']:<20} {entry['trust_score']:<12.2f} {entry['reputation_level']:<12} {entry['transaction_count']:<12}"
                    )
        else:
            click.echo(f"Error: {response.status_code} - {response.text}", err=True)
    except Exception as e:
        logger.error("Error getting leaderboard: %s", e)
        click.echo(f"Error: {str(e)}", err=True)


@reputation.command("trust-score")
@click.argument("agent_id")
@click.option("--format", "json", help="Output format (json, table)")
def trust_score(agent_id: str, format: str):
    """Get detailed trust score breakdown for an agent"""
    import json
    from pathlib import Path

    import requests

    try:
        # Try to get coordinator API URL from config
        config_path = Path.home() / ".aitbc" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_url = config.get("coordinator_api_url", "http://localhost:8203")
        else:
            api_url = "http://localhost:8203"

        response = requests.get(f"{api_url}/reputation/trust-score/{agent_id}", timeout=10)

        if response.status_code == 200:
            data = response.json()
            if format == "json":
                click.echo(json.dumps(data, indent=2))
            else:
                click.echo(f"Agent ID: {data['agent_id']}")
                click.echo(f"Composite Score: {data['composite_score']:.2f}/1000")
                click.echo(f"Performance Score: {data['performance_score']:.2f}/1000")
                click.echo(f"Reliability Score: {data['reliability_score']:.2f}/1000")
                click.echo(f"Community Score: {data['community_score']:.2f}/1000")
                click.echo(f"Security Score: {data['security_score']:.2f}/1000")
                click.echo(f"Economic Score: {data['economic_score']:.2f}/1000")
                click.echo(f"Reputation Level: {data['reputation_level']}")
                click.echo(f"Calculated At: {data['calculated_at']}")
        else:
            click.echo(f"Error: {response.status_code} - {response.text}", err=True)
    except Exception as e:
        logger.error("Error getting trust score: %s", e)
        click.echo(f"Error: {str(e)}", err=True)


@reputation.command("metrics")
@click.option("--format", "json", help="Output format (json, table)")
def metrics(format: str):
    """Get overall reputation system metrics"""
    import json
    from pathlib import Path

    import requests

    try:
        # Try to get coordinator API URL from config
        config_path = Path.home() / ".aitbc" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_url = config.get("coordinator_api_url", "http://localhost:8203")
        else:
            api_url = "http://localhost:8203"

        response = requests.get(f"{api_url}/reputation/metrics", timeout=10)

        if response.status_code == 200:
            data = response.json()
            if format == "json":
                click.echo(json.dumps(data, indent=2))
            else:
                click.echo(f"Total Agents: {data['total_agents']}")
                click.echo(f"Average Trust Score: {data['average_trust_score']:.2f}/1000")
                click.echo("\nLevel Distribution:")
                for level, count in data["level_distribution"].items():
                    click.echo(f"  {level}: {count}")
                click.echo("\nTop Regions:")
                for region in data["top_regions"][:5]:
                    click.echo(f"  {region['region']}: {region['count']}")
                click.echo("\nRecent Activity (24h):")
                click.echo(f"  Events: {data['recent_activity']['events_last_24h']}")
                click.echo(f"  Active Agents: {data['recent_activity']['active_agents']}")
        else:
            click.echo(f"Error: {response.status_code} - {response.text}", err=True)
    except Exception as e:
        logger.error("Error getting metrics: %s", e)
        click.echo(f"Error: {str(e)}", err=True)


@reputation.command("create-profile")
@click.argument("agent_id")
def create_profile(agent_id: str):
    """Create a new reputation profile for an agent"""
    import json
    from pathlib import Path

    import requests

    try:
        # Try to get coordinator API URL from config
        config_path = Path.home() / ".aitbc" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_url = config.get("coordinator_api_url", "http://localhost:8203")
        else:
            api_url = "http://localhost:8203"

        response = requests.post(f"{api_url}/reputation/profile/{agent_id}", timeout=10)

        if response.status_code == 200:
            data = response.json()
            click.echo("Reputation profile created successfully!")
            click.echo(f"Agent ID: {data['agent_id']}")
            click.echo(f"Initial Trust Score: {data['trust_score']}")
            click.echo(f"Reputation Level: {data['reputation_level']}")
            click.echo(f"Created At: {data['created_at']}")
        else:
            click.echo(f"Error: {response.status_code} - {response.text}", err=True)
    except Exception as e:
        logger.error("Error creating profile: %s", e)
        click.echo(f"Error: {str(e)}", err=True)
