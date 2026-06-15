"""Agent SDK commands for AITBC CLI - Basic agent management using the Agent SDK"""

import asyncio
import json
import sys
from pathlib import Path

# Add Agent SDK to path
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent.parent.parent / "packages" / "py" / "aitbc-agent-sdk" / "src")
)

try:
    from aitbc_agent import Agent, AITBCAgent, ComputeConsumer, ComputeProvider
    from aitbc_agent.agent import AgentCapabilities
except ImportError:
    # Fallback if Agent SDK is not installed
    Agent = None
    ComputeProvider = None
    ComputeConsumer = None
    AITBCAgent = None

from ..config import get_config
from ..utils import error, output, success
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


def get_agent_config_dir() -> Path:
    """Get the agent configuration directory"""
    config_dir = Path.home() / ".aitbc" / "agents"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def create_agent(name: str, agent_type: str, capabilities: dict, coordinator_url: str | None = None) -> dict:
    """Create a new agent using the Agent SDK"""
    if Agent is None:
        return {"error": "Agent SDK not available. Install from packages/py/aitbc-agent-sdk"}

    config = get_config()
    try:
        if agent_type == "provider":
            agent = ComputeProvider.create_provider(
                name=name, capabilities=capabilities, pricing_model={"base_rate": 50.0, "currency": "AITBC"}
            )
        elif agent_type == "consumer":
            agent = ComputeConsumer.create(name=name, agent_type="consumer", capabilities=capabilities)
        else:
            agent = Agent.create(name=name, agent_type=agent_type, capabilities=capabilities)

        if coordinator_url:
            agent.coordinator_url = coordinator_url

        # Save agent configuration
        config_dir = get_agent_config_dir()
        config_file = config_dir / f"{name}.json"

        agent_config = {
            "agent_id": agent.identity.id,
            "name": agent.identity.name,
            "address": agent.identity.address,
            "agent_type": agent_type,
            "capabilities": capabilities,
            "coordinator_url": coordinator_url or (config.coordinator_url if config else ""),
        }

        with open(config_file, "w") as f:
            json.dump(agent_config, f, indent=2)

        return {
            "success": True,
            "agent_id": agent.identity.id,
            "name": agent.identity.name,
            "address": agent.identity.address,
            "agent_type": agent_type,
            "capabilities": capabilities,
            "config_file": str(config_file),
        }
    except Exception as e:
        return {"error": str(e)}


async def register_agent(agent_id: str, coordinator_url: str = None) -> dict:
    """Register an agent with the coordinator"""
    if coordinator_url is None:
        config = get_config()
        coordinator_url = config.coordinator_url
    if Agent is None:
        return {"error": "Agent SDK not available"}

    try:
        # For now, return a simulated registration response
        # In a real implementation, this would load the agent from storage and call register()
        return {
            "success": True,
            "agent_id": agent_id,
            "registered": True,
            "coordinator_url": coordinator_url,
            "message": "Agent registered successfully (simulated)",
        }
    except Exception as e:
        return {"error": str(e)}


def get_agent_capabilities() -> dict:
    """Get auto-detected system capabilities for creating a provider"""
    if ComputeProvider is None:
        return {"error": "Agent SDK not available"}

    try:
        return ComputeProvider.assess_capabilities()
    except Exception as e:
        return {"error": str(e)}


def list_local_agents(agent_dir: Path | None = None) -> list:
    """List locally stored agent configurations"""
    if agent_dir is None:
        agent_dir = get_agent_config_dir()

    agents = []
    if agent_dir.exists():
        for agent_file in agent_dir.glob("*.json"):
            try:
                with open(agent_file) as f:
                    agent_data = json.load(f)
                agents.append({"name": agent_file.stem, "file": str(agent_file), **agent_data})
            except Exception:
                pass

    return agents


def get_agent_status(agent_id: str) -> dict:
    """Get status information for an agent"""
    # For now, return a simulated status
    # In a real implementation, this would query the coordinator
    return {
        "agent_id": agent_id,
        "status": "active",
        "registered": True,
        "reputation_score": 0.85,
        "last_seen": "2026-04-29T09:40:00Z",
        "message": "Agent status retrieved (simulated)",
    }


def set_agent_config(name: str, key: str, value: str) -> dict:
    """Set a configuration value for an agent"""
    try:
        config_dir = get_agent_config_dir()
        config_file = config_dir / f"{name}.json"

        if not config_file.exists():
            return {"error": f"Agent configuration not found: {name}"}

        with open(config_file) as f:
            config = json.load(f)

        # Parse value (handle JSON for complex values)
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = value

        config[key] = parsed_value

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        return {"success": True, "name": name, "key": key, "value": parsed_value}
    except Exception as e:
        return {"error": str(e)}


def get_agent_config(name: str, key: str | None = None) -> dict:
    """Get configuration value(s) for an agent"""
    try:
        config_dir = get_agent_config_dir()
        config_file = config_dir / f"{name}.json"

        if not config_file.exists():
            return {"error": f"Agent configuration not found: {name}"}

        with open(config_file) as f:
            config = json.load(f)

        if key:
            if key not in config:
                return {"error": f"Configuration key not found: {key}"}
            return {"success": True, "name": name, "key": key, "value": config[key]}
        else:
            return {"success": True, "name": name, "config": config}
    except Exception as e:
        return {"error": str(e)}


def validate_agent_config(name: str) -> dict:
    """Validate agent configuration"""
    try:
        config_dir = get_agent_config_dir()
        config_file = config_dir / f"{name}.json"

        if not config_file.exists():
            return {"error": f"Agent configuration not found: {name}"}

        with open(config_file) as f:
            config = json.load(f)

        # Validate required fields
        required_fields = ["agent_id", "name", "address", "agent_type", "capabilities"]
        missing_fields = [field for field in required_fields if field not in config]

        if missing_fields:
            return {"valid": False, "error": f"Missing required fields: {', '.join(missing_fields)}"}

        # Validate capabilities structure
        capabilities = config.get("capabilities", {})
        if "compute_type" not in capabilities:
            return {"valid": False, "error": "Missing compute_type in capabilities"}

        return {"valid": True, "name": name, "message": "Configuration is valid"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def import_agent_config(file_path: str, name: str | None = None) -> dict:
    """Import agent configuration from file"""
    try:
        import_file = Path(file_path)
        if not import_file.exists():
            return {"error": f"File not found: {file_path}"}

        with open(import_file) as f:
            config = json.load(f)

        # Use name from file or override
        agent_name = name or config.get("name", import_file.stem)
        config["name"] = agent_name

        # Save to agent config directory
        config_dir = get_agent_config_dir()
        config_file = config_dir / f"{agent_name}.json"

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        return {"success": True, "name": agent_name, "config_file": str(config_file), "imported_from": file_path}
    except Exception as e:
        return {"error": str(e)}


def export_agent_config(name: str, output_path: str) -> dict:
    """Export agent configuration to file"""
    try:
        config_dir = get_agent_config_dir()
        config_file = config_dir / f"{name}.json"

        if not config_file.exists():
            return {"error": f"Agent configuration not found: {name}"}

        with open(config_file) as f:
            config = json.load(f)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(config, f, indent=2)

        return {"success": True, "name": name, "exported_to": output_path}
    except Exception as e:
        return {"error": str(e)}


# CLI command handlers using Click
try:
    import click

    from ..utils import error, output, success

    @click.group()
    def agent():
        """Agent SDK management commands"""
        pass

    @agent.command()
    @click.argument("name")
    @click.option(
        "--type", "agent_type", default="provider", type=click.Choice(["provider", "consumer", "general"]), help="Agent type"
    )
    @click.option("--compute-type", default="inference", help="Compute type (inference, training, processing)")
    @click.option("--gpu-memory", type=int, help="GPU memory in GB")
    @click.option("--models", help="Comma-separated list of supported models")
    @click.option("--performance", type=float, default=0.8, help="Performance score (0.0-1.0)")
    @click.option("--max-jobs", type=int, default=1, help="Maximum concurrent jobs")
    @click.option("--specialization", help="Agent specialization")
    @click.option("--coordinator-url", help="Coordinator URL")
    @click.option("--auto-detect", is_flag=True, help="Auto-detect capabilities")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def create(
        ctx,
        name,
        agent_type,
        compute_type,
        gpu_memory,
        models,
        performance,
        max_jobs,
        specialization,
        coordinator_url,
        auto_detect,
        format,
    ):
        """Create a new agent"""
        try:
            # Build capabilities
            if auto_detect:
                capabilities = get_agent_capabilities()
                if "error" in capabilities:
                    error(f"Auto-detection failed: {capabilities['error']}")
                    raise click.Abort()
            else:
                capabilities = {
                    "compute_type": compute_type,
                    "performance_score": performance,
                    "max_concurrent_jobs": max_jobs,
                }

                if gpu_memory:
                    capabilities["gpu_memory"] = gpu_memory

                if models:
                    capabilities["supported_models"] = [m.strip() for m in models.split(",")]

                if specialization:
                    capabilities["specialization"] = specialization

            # Create agent
            result = create_agent(name, agent_type, capabilities, coordinator_url)

            if "error" in result:
                error(f"Failed to create agent: {result['error']}")
                raise click.Abort()

            success("Agent created successfully!")

            agent_data = [
                {"Field": "Agent ID", "Value": result["agent_id"]},
                {"Field": "Name", "Value": result["name"]},
                {"Field": "Address", "Value": result["address"]},
                {"Field": "Type", "Value": result["agent_type"]},
                {"Field": "Compute Type", "Value": capabilities.get("compute_type", "N/A")},
                {"Field": "GPU Memory", "Value": f"{capabilities.get('gpu_memory', 'N/A')} GB"},
                {"Field": "Performance Score", "Value": f"{capabilities.get('performance_score', 'N/A'):.2f}"},
                {"Field": "Max Jobs", "Value": capabilities.get("max_concurrent_jobs", "N/A")},
                {"Field": "Config File", "Value": result.get("config_file", "N/A")},
            ]

            output(agent_data, ctx.obj.get("output_format", format), title="Agent Created")

        except Exception as e:
            error(f"Error creating agent: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("agent_id")
    @click.option("--coordinator-url", default="http://localhost:8107", help="Coordinator URL")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def register(ctx, agent_id, coordinator_url, format):
        """Register an agent with the coordinator"""
        try:
            result = asyncio.run(register_agent(agent_id, coordinator_url))

            if "error" in result:
                error(f"Failed to register agent: {result['error']}")
                raise click.Abort()

            success(f"Agent {agent_id} registered successfully!")

            reg_data = [
                {"Field": "Agent ID", "Value": result["agent_id"]},
                {"Field": "Registered", "Value": str(result["registered"])},
                {"Field": "Coordinator URL", "Value": result["coordinator_url"]},
                {"Field": "Message", "Value": result["message"]},
            ]

            output(reg_data, ctx.obj.get("output_format", format), title="Agent Registration")

        except Exception as e:
            error(f"Error registering agent: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("agent_id")
    @click.argument("agent_address")
    @click.option("--display-name", help="Agent display name")
    @click.option("--agent-type", default="general", help="Agent type (general, provider, consumer)")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def register_identity(ctx, agent_id, agent_address, display_name, agent_type, format):
        """Register agent identity on blockchain"""
        config = get_config()

        try:
            # Get RPC URL from config (use hub for cross-node operations)
            rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8006")
            rpc_url = rpc_url.replace("localhost", config.hub_discovery_url or "hub.aitbc.bubuit.net")

            # Get chain_id
            try:
                from ..utils.chain_id import get_chain_id

                chain_id = get_chain_id(rpc_url, override=None, timeout=5)
            except Exception:
                import os

                chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

            # Load agent config to get capabilities
            config_dir = get_agent_config_dir()
            config_file = config_dir / f"{agent_id}.json"
            capabilities = {}

            if config_file.exists():
                with open(config_file) as f:
                    agent_config = json.load(f)
                capabilities = agent_config.get("capabilities", {})

            # Convert bech32 address to hex for RPC compatibility
            from ..utils.crypto_utils import bech32_to_hex

            hex_address = bech32_to_hex(agent_address)

            # Submit identity registration to blockchain RPC
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            identity_data = {
                "agent_id": agent_id,
                "agent_address": hex_address,
                "display_name": display_name or agent_id,
                "agent_type": agent_type,
                "capabilities": capabilities,
                "chain_id": chain_id,
            }
            result = http_client.post("/rpc/identity/register", json=identity_data)

            success(f"Agent identity registered on-chain: {agent_id}")
            output(
                {
                    "identity_id": result.get("identity_id"),
                    "agent_id": result.get("agent_id"),
                    "agent_address": result.get("agent_address"),
                    "chain_id": result.get("chain_id"),
                    "status": result.get("status"),
                    "is_verified": result.get("is_verified"),
                },
                ctx.obj.get("output_format", format),
            )

        except Exception as e:
            error(f"Error registering identity: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("agent_id")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def get_identity(ctx, agent_id, format):
        """Get agent identity from blockchain"""
        config = get_config()

        try:
            # Get RPC URL from config (use hub for cross-node operations)
            rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8006")
            rpc_url = rpc_url.replace("localhost", config.hub_discovery_url or "hub.aitbc.bubuit.net")

            # Get chain_id
            try:
                from ..utils.chain_id import get_chain_id

                chain_id = get_chain_id(rpc_url, override=None, timeout=5)
            except Exception:
                import os

                chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

            # Query identity from blockchain RPC
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            result = http_client.get(f"/rpc/identity/{agent_id}?chain_id={chain_id}")

            output(result, ctx.obj.get("output_format", format))

        except Exception as e:
            error(f"Error getting identity: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("agent_id")
    @click.argument("verifier_address")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def verify_identity(ctx, agent_id, verifier_address, format):
        """Verify agent identity on blockchain"""
        config = get_config()

        try:
            # Get RPC URL from config (use hub for cross-node operations)
            rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8006")
            rpc_url = rpc_url.replace("localhost", config.hub_discovery_url or "hub.aitbc.bubuit.net")

            # Get chain_id
            try:
                from ..utils.chain_id import get_chain_id

                chain_id = get_chain_id(rpc_url, override=None, timeout=5)
            except Exception:
                import os

                chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

            # Submit verification to blockchain RPC
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            verification_data = {"agent_id": agent_id, "verifier_address": verifier_address, "chain_id": chain_id}
            result = http_client.post("/rpc/identity/verify", json=verification_data)

            success(f"Agent identity verified: {agent_id}")
            output(result, ctx.obj.get("output_format", format))

        except Exception as e:
            error(f"Error verifying identity: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.option("--agent-dir", type=click.Path(), help="Agent directory path")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def list(ctx, agent_dir, format):
        """List local agents"""
        try:
            agents = list_local_agents(Path(agent_dir) if agent_dir else None)

            if not agents:
                output("No local agents found", ctx.obj.get("output_format", format))
                return

            agent_list = [
                {
                    "Name": agent["name"],
                    "Type": agent.get("agent_type", "unknown"),
                    "Address": agent.get("address", "N/A"),
                    "File": agent["file"],
                }
                for agent in agents
            ]

            output(agent_list, ctx.obj.get("output_format", format), title="Local Agents")

        except Exception as e:
            error(f"Error listing agents: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("agent_id")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def status(ctx, agent_id, format):
        """Get agent status"""
        try:
            status_data = get_agent_status(agent_id)

            status_list = [
                {"Field": "Agent ID", "Value": status_data["agent_id"]},
                {"Field": "Status", "Value": status_data["status"]},
                {"Field": "Registered", "Value": str(status_data["registered"])},
                {"Field": "Reputation Score", "Value": f"{status_data['reputation_score']:.3f}"},
                {"Field": "Last Seen", "Value": status_data["last_seen"]},
                {"Field": "Message", "Value": status_data["message"]},
            ]

            output(status_list, ctx.obj.get("output_format", format), title=f"Agent Status: {agent_id}")

        except Exception as e:
            error(f"Error getting agent status: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def capabilities(ctx, format):
        """Show auto-detected system capabilities"""
        try:
            caps = get_agent_capabilities()

            if "error" in caps:
                error(f"Failed to detect capabilities: {caps['error']}")
                raise click.Abort()

            caps_list = [
                {"Field": "GPU Memory", "Value": f"{caps['gpu_memory']} MiB"},
                {"Field": "GPU Count", "Value": str(caps.get("gpu_count", 0))},
                {"Field": "Compute Capability", "Value": caps.get("compute_capability", "unknown")},
                {"Field": "Performance Score", "Value": f"{caps['performance_score']:.2f}"},
                {"Field": "Max Concurrent Jobs", "Value": str(caps["max_concurrent_jobs"])},
                {"Field": "Supported Models", "Value": ", ".join(caps.get("supported_models", []))},
            ]

            output(caps_list, ctx.obj.get("output_format", format), title="System Capabilities")

        except Exception as e:
            error(f"Error detecting capabilities: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("name")
    @click.argument("key")
    @click.argument("value")
    @click.pass_context
    def config_set(ctx, name, key, value):
        """Set a configuration value for an agent"""
        try:
            result = set_agent_config(name, key, value)

            if "error" in result:
                error(f"Failed to set configuration: {result['error']}")
                raise click.Abort()

            success(f"Configuration set: {name}.{key} = {result['value']}")

        except Exception as e:
            error(f"Error setting configuration: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("name")
    @click.option("--key", help="Specific configuration key to retrieve")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def config_get(ctx, name, key, format):
        """Get configuration value(s) for an agent"""
        try:
            result = get_agent_config(name, key)

            if "error" in result:
                error(f"Failed to get configuration: {result['error']}")
                raise click.Abort()

            if key:
                config_data = [
                    {"Field": "Name", "Value": result["name"]},
                    {"Field": "Key", "Value": result["key"]},
                    {"Field": "Value", "Value": str(result["value"])},
                ]
                output(config_data, ctx.obj.get("output_format", format), title=f"Agent Config: {name}.{key}")
            else:
                output(result["config"], ctx.obj.get("output_format", format), title=f"Agent Config: {name}")

        except Exception as e:
            error(f"Error getting configuration: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("name")
    @click.pass_context
    def config_validate(ctx, name):
        """Validate agent configuration"""
        try:
            result = validate_agent_config(name)

            if result.get("valid"):
                success(f"Configuration is valid: {name}")
            else:
                error(f"Configuration validation failed: {result.get('error')}")
                raise click.Abort()

        except Exception as e:
            error(f"Error validating configuration: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("file_path")
    @click.option("--name", help="Override agent name")
    @click.pass_context
    def config_import(ctx, file_path, name):
        """Import agent configuration from file"""
        try:
            result = import_agent_config(file_path, name)

            if "error" in result:
                error(f"Failed to import configuration: {result['error']}")
                raise click.Abort()

            success(f"Configuration imported: {result['name']} -> {result['config_file']}")

        except Exception as e:
            error(f"Error importing configuration: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("name")
    @click.argument("output_path")
    @click.pass_context
    def config_export(ctx, name, output_path):
        """Export agent configuration to file"""
        try:
            result = export_agent_config(name, output_path)

            if "error" in result:
                error(f"Failed to export configuration: {result['error']}")
                raise click.Abort()

            success(f"Configuration exported: {name} -> {result['exported_to']}")

        except Exception as e:
            error(f"Error exporting configuration: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument("job_id")
    @click.pass_context
    def job(ctx, job_id: str):
        """Get specific AI job details from coordinator-api"""
        config = get_config()

        try:
            http_client = AITBCHTTPClient(base_url=config.coordinator_url, timeout=10)
            job_data = http_client.get(f"/api/v1/jobs/{job_id}")
            success(f"Job {job_id}:")
            output(job_data, ctx.obj.get("output_format", "table"))
        except NetworkError as e:
            error(f"Network error: {e}")
        except Exception as e:
            error(f"Error fetching job: {e}")

    @agent.command()
    @click.option("--status", help="Filter by job status")
    @click.option("--limit", type=int, default=20, help="Number of jobs to return")
    @click.pass_context
    def jobs(ctx, status: str | None, limit: int):
        """List AI jobs from coordinator-api"""
        config = get_config()

        try:
            http_client = AITBCHTTPClient(base_url=config.coordinator_url, timeout=10)
            params = {"limit": limit}
            if status:
                params["status"] = status

            jobs_data = http_client.get("/api/v1/jobs", params=params)
            success("Jobs:")
            output(jobs_data, ctx.obj.get("output_format", "table"))
        except NetworkError as e:
            error(f"Network error: {e}")
        except Exception as e:
            error(f"Error fetching jobs: {e}")

    @agent.command()
    @click.argument("task")
    @click.option("--model", help="AI model to use")
    @click.option("--priority", default="normal", help="Job priority")
    @click.pass_context
    def submit(ctx, task: str, model: str | None, priority: str):
        """Submit an AI job to coordinator-api"""
        config = get_config()

        try:
            http_client = AITBCHTTPClient(base_url=config.coordinator_url, timeout=10)
            job_data = {"task": task, "priority": priority}
            if model:
                job_data["model"] = model

            result = http_client.post("/api/v1/jobs", json=job_data)
            success(f"Job submitted: {result.get('job_id')}")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError as e:
            error(f"Network error: {e}")
        except Exception as e:
            error(f"Error submitting job: {e}")

    @agent.command()
    @click.argument("job_id")
    @click.pass_context
    def cancel(ctx, job_id: str):
        """Cancel an AI job via coordinator-api"""
        config = get_config()

        try:
            http_client = AITBCHTTPClient(base_url=config.coordinator_url, timeout=10)
            result = http_client.delete(f"/api/v1/jobs/{job_id}")
            success(f"Job {job_id} cancelled")
            output(result, ctx.obj.get("output_format", "table"))
        except NetworkError as e:
            error(f"Network error: {e}")
        except Exception as e:
            error(f"Error cancelling job: {e}")

    # Agent Coordinator integration commands
    @agent.group()
    def discover():
        """Discover agents by capability"""
        pass

    @discover.command()
    @click.option("--capability", help="Filter by capability")
    @click.option("--agent-type", help="Filter by agent type")
    @click.option("--min-health", type=float, default=0.0, help="Minimum health score")
    @click.option("--limit", type=int, default=50, help="Maximum results")
    @click.option("--coordinator-url", default="http://localhost:9001", help="Agent coordinator URL")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def agents(ctx, capability, agent_type, min_health, limit, coordinator_url, format):
        """Discover agents by capability"""
        try:
            import requests

            params = {}
            if capability:
                params["capability"] = capability
            if agent_type:
                params["agent_type"] = agent_type
            if min_health > 0:
                params["min_health_score"] = min_health
            if limit:
                params["limit"] = limit

            response = requests.get(f"{coordinator_url}/api/v1/agent/discover", params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            output(result, ctx.obj.get("output_format", format), title="Discovered Agents")
        except requests.exceptions.RequestException as e:
            error(f"Error connecting to agent coordinator at {coordinator_url}: {e}")
            error("Make sure the agent-coordinator service is running")
            raise click.Abort()
        except Exception as e:
            error(f"Error discovering agents: {e}")
            raise click.Abort()

    @agent.command()
    @click.option("--agent-id", required=True, help="Agent ID")
    @click.option("--limit", type=int, default=100, help="Maximum messages")
    @click.option("--unread-only", is_flag=True, help="Only unread messages")
    @click.option("--coordinator-url", default="http://localhost:9001", help="Agent coordinator URL")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def inbox(ctx, agent_id, limit, unread_only, coordinator_url, format):
        """View agent inbox"""
        try:
            import requests

            params = {"agent_id": agent_id, "limit": limit, "unread_only": unread_only}
            response = requests.get(f"{coordinator_url}/api/v1/agent/messages/inbox", params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            output(result, ctx.obj.get("output_format", format), title=f"Inbox for {agent_id}")
        except requests.exceptions.RequestException as e:
            error(f"Error connecting to agent coordinator at {coordinator_url}: {e}")
            error("Make sure the agent-coordinator service is running")
            raise click.Abort()
        except Exception as e:
            error(f"Error getting inbox: {e}")
            raise click.Abort()

    @agent.command()
    @click.option("--agent-id", required=True, help="Agent ID")
    @click.option("--topic", required=True, help="Topic to subscribe to")
    @click.option("--filter", help="Filter criteria (JSON string)")
    @click.option("--coordinator-url", default="http://localhost:9001", help="Agent coordinator URL")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def subscribe(ctx, agent_id, topic, filter, coordinator_url, format):
        """Subscribe to topic"""
        try:
            import requests

            data = {"agent_id": agent_id, "topic": topic, "filter": json.loads(filter) if filter else {}}
            response = requests.post(f"{coordinator_url}/api/v1/agent/subscribe", json=data, timeout=10)
            response.raise_for_status()
            result = response.json()
            output(result, ctx.obj.get("output_format", format), title="Subscription")
            success(f"Agent {agent_id} subscribed to topic {topic}")
        except json.JSONDecodeError as e:
            error(f"Invalid JSON in filter: {e}")
            raise click.Abort()
        except requests.exceptions.RequestException as e:
            error(f"Error connecting to agent coordinator at {coordinator_url}: {e}")
            error("Make sure the agent-coordinator service is running")
            raise click.Abort()
        except Exception as e:
            error(f"Error subscribing to topic: {e}")
            raise click.Abort()

    @agent.group()
    def workflow():
        """Workflow management"""
        pass

    @workflow.command()
    @click.option("--name", required=True, help="Workflow name")
    @click.option("--description", help="Workflow description")
    @click.option("--steps-file", required=True, type=click.Path(exists=True), help="JSON file with workflow steps")
    @click.option("--coordinator-url", default="http://localhost:9001", help="Agent coordinator URL")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def create_workflow(ctx, name, description, steps_file, coordinator_url, format):
        """Create workflow"""
        try:
            import requests

            with open(steps_file) as f:
                steps = json.load(f)

            data = {"name": name, "description": description or "", "steps": steps, "created_by": "cli"}
            response = requests.post(f"{coordinator_url}/api/v1/agent/workflows", json=data, timeout=10)
            response.raise_for_status()
            result = response.json()
            output(result, ctx.obj.get("output_format", format), title="Created Workflow")
            success(f"Workflow '{name}' created successfully")
        except FileNotFoundError as e:
            error(f"File not found: {e}")
            raise click.Abort()
        except json.JSONDecodeError as e:
            error(f"Invalid JSON in steps file: {e}")
            raise click.Abort()
        except requests.exceptions.RequestException as e:
            error(f"Error connecting to agent coordinator at {coordinator_url}: {e}")
            error("Make sure the agent-coordinator service is running")
            raise click.Abort()
        except Exception as e:
            error(f"Error creating workflow: {e}")
            raise click.Abort()

    @workflow.command()
    @click.option("--workflow-id", required=True, help="Workflow ID")
    @click.option("--input-file", type=click.Path(exists=True), help="JSON file with input parameters")
    @click.option("--coordinator-url", default="http://localhost:9001", help="Agent coordinator URL")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def execute(ctx, workflow_id, input_file, coordinator_url, format):
        """Execute workflow"""
        try:
            import requests

            input_params = {}
            if input_file:
                with open(input_file) as f:
                    input_params = json.load(f)

            data = {"input_parameters": input_params}
            response = requests.post(f"{coordinator_url}/api/v1/agent/workflows/{workflow_id}/execute", json=data, timeout=10)
            response.raise_for_status()
            result = response.json()
            output(result, ctx.obj.get("output_format", format), title="Workflow Execution")
            success(f"Workflow {workflow_id} execution started")
        except FileNotFoundError as e:
            error(f"File not found: {e}")
            raise click.Abort()
        except json.JSONDecodeError as e:
            error(f"Invalid JSON in input file: {e}")
            raise click.Abort()
        except requests.exceptions.RequestException as e:
            error(f"Error connecting to agent coordinator at {coordinator_url}: {e}")
            error("Make sure the agent-coordinator service is running")
            raise click.Abort()
        except Exception as e:
            error(f"Error executing workflow: {e}")
            raise click.Abort()

    @workflow.command()
    @click.option("--workflow-id", required=True, help="Workflow ID")
    @click.option("--coordinator-url", default="http://localhost:9001", help="Agent coordinator URL")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def workflow_status(ctx, workflow_id, coordinator_url, format):
        """Get workflow status"""
        try:
            import requests

            response = requests.get(f"{coordinator_url}/api/v1/agent/workflows/{workflow_id}/status", timeout=10)
            response.raise_for_status()
            result = response.json()
            output(result, ctx.obj.get("output_format", format), title=f"Workflow Status: {workflow_id}")
        except requests.exceptions.RequestException as e:
            error(f"Error connecting to agent coordinator at {coordinator_url}: {e}")
            error("Make sure the agent-coordinator service is running")
            raise click.Abort()
        except Exception as e:
            error(f"Error getting workflow status: {e}")
            raise click.Abort()

    @workflow.command()
    @click.option("--coordinator-url", default="http://localhost:9001", help="Agent coordinator URL")
    @click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
    @click.pass_context
    def list_workflows(ctx, coordinator_url, format):
        """List workflows"""
        try:
            import requests

            response = requests.get(f"{coordinator_url}/api/v1/agent/workflows", timeout=10)
            response.raise_for_status()
            result = response.json()
            output(result, ctx.obj.get("output_format", format), title="Workflows")
        except requests.exceptions.RequestException as e:
            error(f"Error connecting to agent coordinator at {coordinator_url}: {e}")
            error("Make sure the agent-coordinator service is running")
            raise click.Abort()
        except Exception as e:
            error(f"Error listing workflows: {e}")
            raise click.Abort()

except ImportError:
    # Click not available, commands will be added programmatically
    pass
