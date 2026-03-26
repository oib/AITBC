"""Cross-chain agent communication commands for AITBC CLI"""

import click
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional
from core.config import load_multichain_config
from core.agent_communication import (
    CrossChainAgentCommunication, AgentInfo, AgentMessage, 
    MessageType, AgentStatus
)
from utils import output, error, success

@click.group()
def agent_comm():
    """Cross-chain agent communication commands"""
    pass

@agent_comm.command()
@click.argument('agent_id')
@click.argument('name')
@click.argument('chain_id')
@click.argument('endpoint')
@click.option('--capabilities', help='Comma-separated list of capabilities')
@click.option('--reputation', default=0.5, help='Initial reputation score')
@click.option('--version', default='1.0.0', help='Agent version')
@click.pass_context
def register(ctx, agent_id, name, chain_id, endpoint, capabilities, reputation, version):
    """Register an agent in the cross-chain network"""
    try:
        config = load_multichain_config()
        comm = CrossChainAgentCommunication(config)
        
        # Parse capabilities
        cap_list = capabilities.split(',') if capabilities else []
        
        # Create agent info
        agent_info = AgentInfo(
            agent_id=agent_id,
            name=name,
            chain_id=chain_id,
            node_id="default-node",  # Would be determined dynamically
            status=AgentStatus.ACTIVE,
            capabilities=cap_list,
            reputation_score=reputation,
            last_seen=datetime.now(),
            endpoint=endpoint,
            version=version
        )
        
        # Register agent
        success = asyncio.run(comm.register_agent(agent_info))
        
        if success:
            success(f"Agent {agent_id} registered successfully!")
            
            agent_data = {
                "Agent ID": agent_id,
                "Name": name,
                "Chain ID": chain_id,
                "Status": "active",
                "Capabilities": ", ".join(cap_list),
                "Reputation": f"{reputation:.2f}",
                "Endpoint": endpoint,
                "Version": version
            }
            
            output(agent_data, ctx.obj.get('output_format', 'table'))
        else:
            error(f"Failed to register agent {agent_id}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error registering agent: {str(e)}")
        raise click.Abort()

@agent_comm.command()
@click.option('--chain-id', help='Filter by chain ID')
@click.option('--status', type=click.Choice(['active', 'inactive', 'busy', 'offline']), help='Filter by status')
@click.option('--capabilities', help='Filter by capabilities (comma-separated)')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def list(ctx, chain_id, status, capabilities, format):
    """List registered agents"""
    try:
        config = load_multichain_config()
        comm = CrossChainAgentCommunication(config)
        
        # Get all agents
        agents = list(comm.agents.values())
        
        # Apply filters
        if chain_id:
            agents = [a for a in agents if a.chain_id == chain_id]
        
        if status:
            agents = [a for a in agents if a.status.value == status]
        
        if capabilities:
            required_caps = [cap.strip() for cap in capabilities.split(',')]
            agents = [a for a in agents if any(cap in a.capabilities for cap in required_caps)]
        
        if not agents:
            output("No agents found", ctx.obj.get('output_format', 'table'))
            return
        
        # Format output
        agent_data = [
            {
                "Agent ID": agent.agent_id,
                "Name": agent.name,
                "Chain ID": agent.chain_id,
                "Status": agent.status.value,
                "Reputation": f"{agent.reputation_score:.2f}",
                "Capabilities": ", ".join(agent.capabilities[:3]),  # Show first 3
                "Last Seen": agent.last_seen.strftime("%Y-%m-%d %H:%M:%S")
            }
            for agent in agents
        ]
        
        output(agent_data, ctx.obj.get('output_format', format), title="Registered Agents")
        
    except Exception as e:
        error(f"Error listing agents: {str(e)}")
        raise click.Abort()

@agent_comm.command()
@click.argument('chain_id')
@click.option('--capabilities', help='Required capabilities (comma-separated)')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def discover(ctx, chain_id, capabilities, format):
    """Discover agents on a specific chain"""
    try:
        config = load_multichain_config()
        comm = CrossChainAgentCommunication(config)
        
        # Parse capabilities
        cap_list = capabilities.split(',') if capabilities else None
        
        # Discover agents
        agents = asyncio.run(comm.discover_agents(chain_id, cap_list))
        
        if not agents:
            output(f"No agents found on chain {chain_id}", ctx.obj.get('output_format', 'table'))
            return
        
        # Format output
        agent_data = [
            {
                "Agent ID": agent.agent_id,
                "Name": agent.name,
                "Status": agent.status.value,
                "Reputation": f"{agent.reputation_score:.2f}",
                "Capabilities": ", ".join(agent.capabilities),
                "Endpoint": agent.endpoint,
                "Version": agent.version
            }
            for agent in agents
        ]
        
        output(agent_data, ctx.obj.get('output_format', format), title=f"Agents on Chain {chain_id}")
        
    except Exception as e:
        error(f"Error discovering agents: {str(e)}")
        raise click.Abort()

@agent_comm.command()
@click.argument('sender_id')
@click.argument('receiver_id')
@click.argument('message_type')
@click.argument('chain_id')
@click.option('--payload', help='Message payload (JSON string)')
@click.option('--target-chain', help='Target chain for cross-chain messages')
@click.option('--priority', default=5, help='Message priority (1-10)')
@click.option('--ttl', default=3600, help='Time to live in seconds')
@click.pass_context
def send(ctx, sender_id, receiver_id, message_type, chain_id, payload, target_chain, priority, ttl):
    """Send a message to an agent"""
    try:
        config = load_multichain_config()
        comm = CrossChainAgentCommunication(config)
        
        # Parse message type
        try:
            msg_type = MessageType(message_type)
        except ValueError:
            error(f"Invalid message type: {message_type}")
            error(f"Valid types: {[t.value for t in MessageType]}")
            raise click.Abort()
        
        # Parse payload
        payload_dict = {}
        if payload:
            try:
                payload_dict = json.loads(payload)
            except json.JSONDecodeError:
                error("Invalid JSON payload")
                raise click.Abort()
        
        # Create message
        message = AgentMessage(
            message_id=f"msg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{sender_id}",
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=msg_type,
            chain_id=chain_id,
            target_chain_id=target_chain,
            payload=payload_dict,
            timestamp=datetime.now(),
            signature="auto_generated",  # Would be cryptographically signed
            priority=priority,
            ttl_seconds=ttl
        )
        
        # Send message
        success = asyncio.run(comm.send_message(message))
        
        if success:
            success(f"Message sent successfully to {receiver_id}")
            
            message_data = {
                "Message ID": message.message_id,
                "Sender": sender_id,
                "Receiver": receiver_id,
                "Type": message_type,
                "Chain": chain_id,
                "Target Chain": target_chain or "Same",
                "Priority": priority,
                "TTL": f"{ttl}s",
                "Sent": message.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            output(message_data, ctx.obj.get('output_format', 'table'))
        else:
            error(f"Failed to send message to {receiver_id}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error sending message: {str(e)}")
        raise click.Abort()

@agent_comm.command()
@click.argument('agent_ids', nargs=-1, required=True)
@click.argument('collaboration_type')
@click.option('--governance', help='Governance rules (JSON string)')
@click.pass_context
def collaborate(ctx, agent_ids, collaboration_type, governance):
    """Create a multi-agent collaboration"""
    try:
        config = load_multichain_config()
        comm = CrossChainAgentCommunication(config)
        
        # Parse governance rules
        governance_dict = {}
        if governance:
            try:
                governance_dict = json.loads(governance)
            except json.JSONDecodeError:
                error("Invalid JSON governance rules")
                raise click.Abort()
        
        # Create collaboration
        collaboration_id = asyncio.run(comm.create_collaboration(
            list(agent_ids), collaboration_type, governance_dict
        ))
        
        if collaboration_id:
            success(f"Collaboration created: {collaboration_id}")
            
            collab_data = {
                "Collaboration ID": collaboration_id,
                "Type": collaboration_type,
                "Participants": ", ".join(agent_ids),
                "Status": "active",
                "Created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            output(collab_data, ctx.obj.get('output_format', 'table'))
        else:
            error("Failed to create collaboration")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error creating collaboration: {str(e)}")
        raise click.Abort()

@agent_comm.command()
@click.argument('agent_id')
@click.argument('interaction_result', type=click.Choice(['success', 'failure']))
@click.option('--feedback', type=float, help='Feedback score (0.0-1.0)')
@click.pass_context
def reputation(ctx, agent_id, interaction_result, feedback):
    """Update agent reputation"""
    try:
        config = load_multichain_config()
        comm = CrossChainAgentCommunication(config)
        
        # Update reputation
        success = asyncio.run(comm.update_reputation(
            agent_id, interaction_result == 'success', feedback
        ))
        
        if success:
            # Get updated reputation
            agent_status = asyncio.run(comm.get_agent_status(agent_id))
            
            if agent_status and agent_status.get('reputation'):
                rep = agent_status['reputation']
                success(f"Reputation updated for {agent_id}")
                
                rep_data = {
                    "Agent ID": agent_id,
                    "Reputation Score": f"{rep['reputation_score']:.3f}",
                    "Total Interactions": rep['total_interactions'],
                    "Successful": rep['successful_interactions'],
                    "Failed": rep['failed_interactions'],
                    "Success Rate": f"{(rep['successful_interactions'] / rep['total_interactions'] * 100):.1f}%" if rep['total_interactions'] > 0 else "N/A",
                    "Last Updated": rep['last_updated']
                }
                
                output(rep_data, ctx.obj.get('output_format', 'table'))
            else:
                success(f"Reputation updated for {agent_id}")
        else:
            error(f"Failed to update reputation for {agent_id}")
            raise click.Abort()
        
    except Exception as e:
        error(f"Error updating reputation: {str(e)}")
        raise click.Abort()

@agent_comm.command()
@click.argument('agent_id')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def status(ctx, agent_id, format):
    """Get detailed agent status"""
    try:
        config = load_multichain_config()
        comm = CrossChainAgentCommunication(config)
        
        # Get agent status
        agent_status = asyncio.run(comm.get_agent_status(agent_id))
        
        if not agent_status:
            error(f"Agent {agent_id} not found")
            raise click.Abort()
        
        # Format output
        status_data = [
            {"Metric": "Agent ID", "Value": agent_status["agent_info"]["agent_id"]},
            {"Metric": "Name", "Value": agent_status["agent_info"]["name"]},
            {"Metric": "Chain ID", "Value": agent_status["agent_info"]["chain_id"]},
            {"Metric": "Status", "Value": agent_status["status"]},
            {"Metric": "Reputation", "Value": f"{agent_status['agent_info']['reputation_score']:.3f}" if agent_status.get('reputation') else "N/A"},
            {"Metric": "Capabilities", "Value": ", ".join(agent_status["agent_info"]["capabilities"])},
            {"Metric": "Message Queue Size", "Value": agent_status["message_queue_size"]},
            {"Metric": "Active Collaborations", "Value": agent_status["active_collaborations"]},
            {"Metric": "Last Seen", "Value": agent_status["last_seen"]},
            {"Metric": "Endpoint", "Value": agent_status["agent_info"]["endpoint"]},
            {"Metric": "Version", "Value": agent_status["agent_info"]["version"]}
        ]
        
        output(status_data, ctx.obj.get('output_format', format), title=f"Agent Status: {agent_id}")
        
    except Exception as e:
        error(f"Error getting agent status: {str(e)}")
        raise click.Abort()

@agent_comm.command()
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def network(ctx, format):
    """Get cross-chain network overview"""
    try:
        config = load_multichain_config()
        comm = CrossChainAgentCommunication(config)
        
        # Get network overview
        overview = asyncio.run(comm.get_network_overview())
        
        if not overview:
            error("No network data available")
            raise click.Abort()
        
        # Overview data
        overview_data = [
            {"Metric": "Total Agents", "Value": overview["total_agents"]},
            {"Metric": "Active Agents", "Value": overview["active_agents"]},
            {"Metric": "Total Collaborations", "Value": overview["total_collaborations"]},
            {"Metric": "Active Collaborations", "Value": overview["active_collaborations"]},
            {"Metric": "Total Messages", "Value": overview["total_messages"]},
            {"Metric": "Queued Messages", "Value": overview["queued_messages"]},
            {"Metric": "Average Reputation", "Value": f"{overview['average_reputation']:.3f}"},
            {"Metric": "Routing Table Size", "Value": overview["routing_table_size"]},
            {"Metric": "Discovery Cache Size", "Value": overview["discovery_cache_size"]}
        ]
        
        output(overview_data, ctx.obj.get('output_format', format), title="Network Overview")
        
        # Agents by chain
        if overview["agents_by_chain"]:
            chain_data = [
                {"Chain ID": chain_id, "Total Agents": count, "Active Agents": overview["active_agents_by_chain"].get(chain_id, 0)}
                for chain_id, count in overview["agents_by_chain"].items()
            ]
            
            output(chain_data, ctx.obj.get('output_format', format), title="Agents by Chain")
        
        # Collaborations by type
        if overview["collaborations_by_type"]:
            collab_data = [
                {"Type": collab_type, "Count": count}
                for collab_type, count in overview["collaborations_by_type"].items()
            ]
            
            output(collab_data, ctx.obj.get('output_format', format), title="Collaborations by Type")
        
    except Exception as e:
        error(f"Error getting network overview: {str(e)}")
        raise click.Abort()

@agent_comm.command()
@click.option('--realtime', is_flag=True, help='Real-time monitoring')
@click.option('--interval', default=10, help='Update interval in seconds')
@click.pass_context
def monitor(ctx, realtime, interval):
    """Monitor cross-chain agent communication"""
    try:
        config = load_multichain_config()
        comm = CrossChainAgentCommunication(config)
        
        if realtime:
            # Real-time monitoring
            from rich.console import Console
            from rich.live import Live
            from rich.table import Table
            import time
            
            console = Console()
            
            def generate_monitor_table():
                try:
                    overview = asyncio.run(comm.get_network_overview())
                    
                    table = Table(title=f"Agent Network Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    table.add_column("Metric", style="cyan")
                    table.add_column("Value", style="green")
                    
                    table.add_row("Total Agents", str(overview["total_agents"]))
                    table.add_row("Active Agents", str(overview["active_agents"]))
                    table.add_row("Active Collaborations", str(overview["active_collaborations"]))
                    table.add_row("Queued Messages", str(overview["queued_messages"]))
                    table.add_row("Avg Reputation", f"{overview['average_reputation']:.3f}")
                    
                    # Add top chains by agent count
                    if overview["agents_by_chain"]:
                        table.add_row("", "")
                        table.add_row("Top Chains by Agents", "")
                        for chain_id, count in sorted(overview["agents_by_chain"].items(), key=lambda x: x[1], reverse=True)[:3]:
                            active = overview["active_agents_by_chain"].get(chain_id, 0)
                            table.add_row(f"  {chain_id}", f"{count} total, {active} active")
                    
                    return table
                except Exception as e:
                    return f"Error getting network data: {e}"
            
            with Live(generate_monitor_table(), refresh_per_second=1) as live:
                try:
                    while True:
                        live.update(generate_monitor_table())
                        time.sleep(interval)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Monitoring stopped by user[/yellow]")
        else:
            # Single snapshot
            overview = asyncio.run(comm.get_network_overview())
            
            monitor_data = [
                {"Metric": "Total Agents", "Value": overview["total_agents"]},
                {"Metric": "Active Agents", "Value": overview["active_agents"]},
                {"Metric": "Total Collaborations", "Value": overview["total_collaborations"]},
                {"Metric": "Active Collaborations", "Value": overview["active_collaborations"]},
                {"Metric": "Total Messages", "Value": overview["total_messages"]},
                {"Metric": "Queued Messages", "Value": overview["queued_messages"]},
                {"Metric": "Average Reputation", "Value": f"{overview['average_reputation']:.3f}"},
                {"Metric": "Routing Table Size", "Value": overview["routing_table_size"]}
            ]
            
            output(monitor_data, ctx.obj.get('output_format', 'table'), title="Agent Network Monitor")
        
    except Exception as e:
        error(f"Error during monitoring: {str(e)}")
        raise click.Abort()
