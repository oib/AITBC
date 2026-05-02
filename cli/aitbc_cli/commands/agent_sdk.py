"""Agent SDK commands for AITBC CLI - Basic agent management using the Agent SDK"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

# Add Agent SDK to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent / "packages" / "py" / "aitbc-agent-sdk" / "src"))

try:
    from aitbc_agent import Agent, ComputeProvider, ComputeConsumer, AITBCAgent
    from aitbc_agent.agent import AgentCapabilities
except ImportError:
    # Fallback if Agent SDK is not installed
    Agent = None
    ComputeProvider = None
    ComputeConsumer = None
    AITBCAgent = None


def get_agent_config_dir() -> Path:
    """Get the agent configuration directory"""
    config_dir = Path.home() / ".aitbc" / "agents"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def create_agent(name: str, agent_type: str, capabilities: dict, coordinator_url: Optional[str] = None) -> dict:
    """Create a new agent using the Agent SDK"""
    if Agent is None:
        return {"error": "Agent SDK not available. Install from packages/py/aitbc-agent-sdk"}
    
    try:
        if agent_type == "provider":
            agent = ComputeProvider.create_provider(
                name=name,
                capabilities=capabilities,
                pricing_model={"base_rate": 50.0, "currency": "AITBC"}
            )
        elif agent_type == "consumer":
            agent = ComputeConsumer.create(
                name=name,
                agent_type="consumer",
                capabilities=capabilities
            )
        else:
            agent = Agent.create(
                name=name,
                agent_type=agent_type,
                capabilities=capabilities
            )
        
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
            "coordinator_url": coordinator_url or "http://localhost:8001"
        }
        
        with open(config_file, 'w') as f:
            json.dump(agent_config, f, indent=2)
        
        return {
            "success": True,
            "agent_id": agent.identity.id,
            "name": agent.identity.name,
            "address": agent.identity.address,
            "agent_type": agent_type,
            "capabilities": capabilities,
            "config_file": str(config_file)
        }
    except Exception as e:
        return {"error": str(e)}


async def register_agent(agent_id: str, coordinator_url: str = "http://localhost:8001") -> dict:
    """Register an agent with the coordinator"""
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
            "message": "Agent registered successfully (simulated)"
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


def list_local_agents(agent_dir: Optional[Path] = None) -> list:
    """List locally stored agent configurations"""
    if agent_dir is None:
        agent_dir = get_agent_config_dir()
    
    agents = []
    if agent_dir.exists():
        for agent_file in agent_dir.glob("*.json"):
            try:
                with open(agent_file) as f:
                    agent_data = json.load(f)
                agents.append({
                    "name": agent_file.stem,
                    "file": str(agent_file),
                    **agent_data
                })
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
        "message": "Agent status retrieved (simulated)"
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
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        return {
            "success": True,
            "name": name,
            "key": key,
            "value": parsed_value
        }
    except Exception as e:
        return {"error": str(e)}


def get_agent_config(name: str, key: Optional[str] = None) -> dict:
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
            return {
                "success": True,
                "name": name,
                "key": key,
                "value": config[key]
            }
        else:
            return {
                "success": True,
                "name": name,
                "config": config
            }
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
            return {
                "valid": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }
        
        # Validate capabilities structure
        capabilities = config.get("capabilities", {})
        if "compute_type" not in capabilities:
            return {
                "valid": False,
                "error": "Missing compute_type in capabilities"
            }
        
        return {
            "valid": True,
            "name": name,
            "message": "Configuration is valid"
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def import_agent_config(file_path: str, name: Optional[str] = None) -> dict:
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
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        return {
            "success": True,
            "name": agent_name,
            "config_file": str(config_file),
            "imported_from": file_path
        }
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
        
        with open(output_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        return {
            "success": True,
            "name": name,
            "exported_to": output_path
        }
    except Exception as e:
        return {"error": str(e)}


# CLI command handlers using Click
try:
    import click
    from ..utils import output, error, success
    
    @click.group()
    def agent():
        """Agent SDK management commands"""
        pass
    
    @agent.command()
    @click.argument('name')
    @click.option('--type', 'agent_type', default='provider', type=click.Choice(['provider', 'consumer', 'general']), help='Agent type')
    @click.option('--compute-type', default='inference', help='Compute type (inference, training, processing)')
    @click.option('--gpu-memory', type=int, help='GPU memory in GB')
    @click.option('--models', help='Comma-separated list of supported models')
    @click.option('--performance', type=float, default=0.8, help='Performance score (0.0-1.0)')
    @click.option('--max-jobs', type=int, default=1, help='Maximum concurrent jobs')
    @click.option('--specialization', help='Agent specialization')
    @click.option('--coordinator-url', help='Coordinator URL')
    @click.option('--auto-detect', is_flag=True, help='Auto-detect capabilities')
    @click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
    @click.pass_context
    def create(ctx, name, agent_type, compute_type, gpu_memory, models, performance, max_jobs, specialization, coordinator_url, auto_detect, format):
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
                    "max_concurrent_jobs": max_jobs
                }
                
                if gpu_memory:
                    capabilities["gpu_memory"] = gpu_memory
                
                if models:
                    capabilities["supported_models"] = [m.strip() for m in models.split(',')]
                
                if specialization:
                    capabilities["specialization"] = specialization
            
            # Create agent
            result = create_agent(name, agent_type, capabilities, coordinator_url)
            
            if "error" in result:
                error(f"Failed to create agent: {result['error']}")
                raise click.Abort()
            
            success(f"Agent created successfully!")
            
            agent_data = [
                {"Field": "Agent ID", "Value": result["agent_id"]},
                {"Field": "Name", "Value": result["name"]},
                {"Field": "Address", "Value": result["address"]},
                {"Field": "Type", "Value": result["agent_type"]},
                {"Field": "Compute Type", "Value": capabilities.get("compute_type", "N/A")},
                {"Field": "GPU Memory", "Value": f"{capabilities.get('gpu_memory', 'N/A')} GB"},
                {"Field": "Performance Score", "Value": f"{capabilities.get('performance_score', 'N/A'):.2f}"},
                {"Field": "Max Jobs", "Value": capabilities.get("max_concurrent_jobs", "N/A")},
                {"Field": "Config File", "Value": result.get("config_file", "N/A")}
            ]
            
            output(agent_data, ctx.obj.get('output_format', format), title="Agent Created")
            
        except Exception as e:
            error(f"Error creating agent: {str(e)}")
            raise click.Abort()
    
    @agent.command()
    @click.argument('agent_id')
    @click.option('--coordinator-url', default='http://localhost:9001', help='Coordinator URL')
    @click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
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
                {"Field": "Message", "Value": result["message"]}
            ]
            
            output(reg_data, ctx.obj.get('output_format', format), title="Agent Registration")
            
        except Exception as e:
            error(f"Error registering agent: {str(e)}")
            raise click.Abort()
    
    @agent.command()
    @click.option('--agent-dir', type=click.Path(), help='Agent directory path')
    @click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
    @click.pass_context
    def list(ctx, agent_dir, format):
        """List local agents"""
        try:
            agents = list_local_agents(Path(agent_dir) if agent_dir else None)
            
            if not agents:
                output("No local agents found", ctx.obj.get('output_format', format))
                return
            
            agent_list = [
                {
                    "Name": agent["name"],
                    "Type": agent.get("agent_type", "unknown"),
                    "Address": agent.get("address", "N/A"),
                    "File": agent["file"]
                }
                for agent in agents
            ]
            
            output(agent_list, ctx.obj.get('output_format', format), title="Local Agents")
            
        except Exception as e:
            error(f"Error listing agents: {str(e)}")
            raise click.Abort()
    
    @agent.command()
    @click.argument('agent_id')
    @click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
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
                {"Field": "Message", "Value": status_data["message"]}
            ]
            
            output(status_list, ctx.obj.get('output_format', format), title=f"Agent Status: {agent_id}")
            
        except Exception as e:
            error(f"Error getting agent status: {str(e)}")
            raise click.Abort()
    
    @agent.command()
    @click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
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
                {"Field": "GPU Count", "Value": str(caps.get('gpu_count', 0))},
                {"Field": "Compute Capability", "Value": caps.get('compute_capability', 'unknown')},
                {"Field": "Performance Score", "Value": f"{caps['performance_score']:.2f}"},
                {"Field": "Max Concurrent Jobs", "Value": str(caps['max_concurrent_jobs'])},
                {"Field": "Supported Models", "Value": ", ".join(caps.get('supported_models', []))}
            ]
            
            output(caps_list, ctx.obj.get('output_format', format), title="System Capabilities")
            
        except Exception as e:
            error(f"Error detecting capabilities: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument('name')
    @click.argument('key')
    @click.argument('value')
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
    @click.argument('name')
    @click.option('--key', help='Specific configuration key to retrieve')
    @click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
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
                    {"Field": "Value", "Value": str(result["value"])}
                ]
                output(config_data, ctx.obj.get('output_format', format), title=f"Agent Config: {name}.{key}")
            else:
                output(result["config"], ctx.obj.get('output_format', format), title=f"Agent Config: {name}")
            
        except Exception as e:
            error(f"Error getting configuration: {str(e)}")
            raise click.Abort()

    @agent.command()
    @click.argument('name')
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
    @click.argument('file_path')
    @click.option('--name', help='Override agent name')
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
    @click.argument('name')
    @click.argument('output_path')
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

except ImportError:
    # Click not available, commands will be added programmatically
    pass
