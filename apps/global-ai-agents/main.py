"""
Global AI Agent Communication Service for AITBC
Handles cross-chain and cross-region AI agent communication with global optimization
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from aitbc import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="AITBC Global AI Agent Communication Service",
    description="Global AI agent communication and collaboration platform",
    version="1.0.0"
)

# Data models
class Agent(BaseModel):
    agent_id: str
    name: str
    type: str  # ai, blockchain, oracle, market_maker, etc.
    region: str
    capabilities: List[str]
    status: str  # active, inactive, busy
    languages: List[str]  # Languages the agent can communicate in
    specialization: str
    performance_score: float

class AgentMessage(BaseModel):
    message_id: str
    sender_id: str
    recipient_id: Optional[str]  # None for broadcast
    message_type: str  # request, response, collaboration, data_share
    content: Dict[str, Any]
    priority: str  # low, medium, high, critical
    language: str
    timestamp: datetime
    encryption_key: Optional[str] = None

class CollaborationSession(BaseModel):
    session_id: str
    participants: List[str]
    session_type: str  # task_force, research, trading, governance
    objective: str
    created_at: datetime
    expires_at: datetime
    status: str  # active, completed, expired

class AgentPerformance(BaseModel):
    agent_id: str
    timestamp: datetime
    tasks_completed: int
    response_time_ms: float
    accuracy_score: float
    collaboration_score: float
    resource_usage: Dict[str, float]

# In-memory storage (in production, use database)
global_agents: Dict[str, Dict] = {}
agent_messages: Dict[str, List[Dict]] = {}
collaboration_sessions: Dict[str, Dict] = {}
agent_performance: Dict[str, List[Dict]] = {}
global_network_stats: Dict[str, Any] = {}

@app.get("/")
async def root():
    return {
        "service": "AITBC Global AI Agent Communication Service",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "total_agents": len(global_agents),
        "active_agents": len([a for a in global_agents.values() if a["status"] == "active"]),
        "active_sessions": len([s for s in collaboration_sessions.values() if s["status"] == "active"]),
        "total_messages": sum(len(messages) for messages in agent_messages.values())
    }

@app.post("/api/v1/agents/register")
async def register_agent(agent: Agent):
    """Register a new AI agent in the global network"""
    if agent.agent_id in global_agents:
        raise HTTPException(status_code=400, detail="Agent already registered")
    
    # Create agent record
    agent_record = {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "type": agent.type,
        "region": agent.region,
        "capabilities": agent.capabilities,
        "status": agent.status,
        "languages": agent.languages,
        "specialization": agent.specialization,
        "performance_score": agent.performance_score,
        "created_at": datetime.utcnow().isoformat(),
        "last_active": datetime.utcnow().isoformat(),
        "total_messages_sent": 0,
        "total_messages_received": 0,
        "collaborations_participated": 0,
        "tasks_completed": 0,
        "reputation_score": 5.0,
        "network_connections": []
    }
    
    global_agents[agent.agent_id] = agent_record
    agent_messages[agent.agent_id] = []
    
    logger.info(f"Agent registered: {agent.name} ({agent.agent_id}) in {agent.region}")
    
    return {
        "agent_id": agent.agent_id,
        "status": "registered",
        "name": agent.name,
        "region": agent.region,
        "created_at": agent_record["created_at"]
    }

@app.get("/api/v1/agents")
async def list_agents(region: Optional[str] = None, 
                     agent_type: Optional[str] = None,
                     status: Optional[str] = None):
    """List all agents with filtering"""
    agents = list(global_agents.values())
    
    # Apply filters
    if region:
        agents = [a for a in agents if a["region"] == region]
    if agent_type:
        agents = [a for a in agents if a["type"] == agent_type]
    if status:
        agents = [a for a in agents if a["status"] == status]
    
    return {
        "agents": agents,
        "total_agents": len(agents),
        "filters": {
            "region": region,
            "agent_type": agent_type,
            "status": status
        }
    }

@app.get("/api/v1/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get detailed agent information"""
    if agent_id not in global_agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = global_agents[agent_id].copy()
    
    # Add recent messages
    agent["recent_messages"] = agent_messages.get(agent_id, [])[-10:]
    
    # Add performance metrics
    agent["performance_metrics"] = agent_performance.get(agent_id, [])
    
    return agent

@app.post("/api/v1/messages/send")
async def send_message(message: AgentMessage):
    """Send a message from one agent to another or broadcast"""
    # Validate sender
    if message.sender_id not in global_agents:
        raise HTTPException(status_code=400, detail="Sender agent not found")
    
    # Create message record
    message_record = {
        "message_id": message.message_id,
        "sender_id": message.sender_id,
        "recipient_id": message.recipient_id,
        "message_type": message.message_type,
        "content": message.content,
        "priority": message.priority,
        "language": message.language,
        "timestamp": message.timestamp.isoformat(),
        "encryption_key": message.encryption_key,
        "status": "delivered",
        "delivered_at": datetime.utcnow().isoformat(),
        "read_at": None
    }
    
    # Handle broadcast
    if message.recipient_id is None:
        # Broadcast to all active agents
        for agent_id in global_agents:
            if agent_id != message.sender_id and global_agents[agent_id]["status"] == "active":
                if agent_id not in agent_messages:
                    agent_messages[agent_id] = []
                agent_messages[agent_id].append(message_record.copy())
        
        # Update sender stats
        global_agents[message.sender_id]["total_messages_sent"] += len(global_agents) - 1
        
        logger.info(f"Broadcast message sent from {message.sender_id} to all agents")
        
    else:
        # Direct message
        if message.recipient_id not in global_agents:
            raise HTTPException(status_code=400, detail="Recipient agent not found")
        
        if message.recipient_id not in agent_messages:
            agent_messages[message.recipient_id] = []
        
        agent_messages[message.recipient_id].append(message_record)
        
        # Update stats
        global_agents[message.sender_id]["total_messages_sent"] += 1
        global_agents[message.recipient_id]["total_messages_received"] += 1
        
        logger.info(f"Message sent from {message.sender_id} to {message.recipient_id}")
    
    return {
        "message_id": message.message_id,
        "status": "delivered",
        "delivered_at": message_record["delivered_at"]
    }

@app.get("/api/v1/messages/{agent_id}")
async def get_agent_messages(agent_id: str, limit: int = 50):
    """Get messages for an agent"""
    if agent_id not in global_agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    messages = agent_messages.get(agent_id, [])
    
    # Sort by timestamp (most recent first)
    messages.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return {
        "agent_id": agent_id,
        "messages": messages[:limit],
        "total_messages": len(messages),
        "unread_count": len([m for m in messages if m.get("read_at") is None])
    }

@app.post("/api/v1/collaborations/create")
async def create_collaboration(session: CollaborationSession):
    """Create a new collaboration session"""
    # Validate participants
    for participant_id in session.participants:
        if participant_id not in global_agents:
            raise HTTPException(status_code=400, detail=f"Participant {participant_id} not found")
    
    # Create collaboration session
    session_record = {
        "session_id": session.session_id,
        "participants": session.participants,
        "session_type": session.session_type,
        "objective": session.objective,
        "created_at": session.created_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
        "status": session.status,
        "messages": [],
        "shared_resources": {},
        "task_progress": {},
        "outcome": None
    }
    
    collaboration_sessions[session.session_id] = session_record
    
    # Update participant stats
    for participant_id in session.participants:
        global_agents[participant_id]["collaborations_participated"] += 1
    
    # Notify participants
    notification = {
        "type": "collaboration_invite",
        "session_id": session.session_id,
        "objective": session.objective,
        "participants": session.participants
    }
    
    for participant_id in session.participants:
        message_record = {
            "message_id": f"collab_{int(datetime.utcnow().timestamp())}",
            "sender_id": "system",
            "recipient_id": participant_id,
            "message_type": "notification",
            "content": notification,
            "priority": "medium",
            "language": "english",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "delivered",
            "delivered_at": datetime.utcnow().isoformat()
        }
        
        if participant_id not in agent_messages:
            agent_messages[participant_id] = []
        agent_messages[participant_id].append(message_record)
    
    logger.info(f"Collaboration session created: {session.session_id} with {len(session.participants)} participants")
    
    return {
        "session_id": session.session_id,
        "status": "created",
        "participants": session.participants,
        "objective": session.objective,
        "created_at": session_record["created_at"]
    }

@app.get("/api/v1/collaborations/{session_id}")
async def get_collaboration(session_id: str):
    """Get collaboration session details"""
    if session_id not in collaboration_sessions:
        raise HTTPException(status_code=404, detail="Collaboration session not found")
    
    return collaboration_sessions[session_id]

@app.post("/api/v1/collaborations/{session_id}/message")
async def send_collaboration_message(session_id: str, sender_id: str, content: Dict[str, Any]):
    """Send a message within a collaboration session"""
    if session_id not in collaboration_sessions:
        raise HTTPException(status_code=404, detail="Collaboration session not found")
    
    if sender_id not in collaboration_sessions[session_id]["participants"]:
        raise HTTPException(status_code=400, detail="Sender not a participant in this session")
    
    # Create collaboration message
    message_record = {
        "message_id": f"collab_msg_{int(datetime.utcnow().timestamp())}",
        "sender_id": sender_id,
        "session_id": session_id,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
        "type": "collaboration_message"
    }
    
    collaboration_sessions[session_id]["messages"].append(message_record)
    
    # Notify all participants
    for participant_id in collaboration_sessions[session_id]["participants"]:
        if participant_id != sender_id:
            notification = {
                "type": "collaboration_message",
                "session_id": session_id,
                "sender_id": sender_id,
                "content": content
            }
            
            msg_record = {
                "message_id": f"notif_{int(datetime.utcnow().timestamp())}",
                "sender_id": "system",
                "recipient_id": participant_id,
                "message_type": "notification",
                "content": notification,
                "priority": "medium",
                "language": "english",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "delivered",
                "delivered_at": datetime.utcnow().isoformat()
            }
            
            if participant_id not in agent_messages:
                agent_messages[participant_id] = []
            agent_messages[participant_id].append(msg_record)
    
    return {
        "message_id": message_record["message_id"],
        "status": "delivered",
        "timestamp": message_record["timestamp"]
    }

@app.post("/api/v1/performance/record")
async def record_agent_performance(performance: AgentPerformance):
    """Record performance metrics for an agent"""
    if performance.agent_id not in global_agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Create performance record
    performance_record = {
        "performance_id": f"perf_{int(datetime.utcnow().timestamp())}",
        "agent_id": performance.agent_id,
        "timestamp": performance.timestamp.isoformat(),
        "tasks_completed": performance.tasks_completed,
        "response_time_ms": performance.response_time_ms,
        "accuracy_score": performance.accuracy_score,
        "collaboration_score": performance.collaboration_score,
        "resource_usage": performance.resource_usage
    }
    
    if performance.agent_id not in agent_performance:
        agent_performance[performance.agent_id] = []
    
    agent_performance[performance.agent_id].append(performance_record)
    
    # Update agent's performance score
    recent_performances = agent_performance[performance.agent_id][-10:]  # Last 10 records
    if recent_performances:
        avg_accuracy = sum(p["accuracy_score"] for p in recent_performances) / len(recent_performances)
        avg_collaboration = sum(p["collaboration_score"] for p in recent_performances) / len(recent_performances)
        
        # Update overall performance score
        new_score = (avg_accuracy * 0.6 + avg_collaboration * 0.4)
        global_agents[performance.agent_id]["performance_score"] = round(new_score, 2)
        
        # Update tasks completed
        global_agents[performance.agent_id]["tasks_completed"] += performance.tasks_completed
    
    return {
        "performance_id": performance_record["performance_id"],
        "status": "recorded",
        "updated_performance_score": global_agents[performance.agent_id]["performance_score"]
    }

@app.get("/api/v1/performance/{agent_id}")
async def get_agent_performance(agent_id: str, hours: int = 24):
    """Get performance metrics for an agent"""
    if agent_id not in global_agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    performance_records = agent_performance.get(agent_id, [])
    recent_performance = [
        p for p in performance_records
        if datetime.fromisoformat(p["timestamp"]) > cutoff_time
    ]
    
    # Calculate statistics
    if recent_performance:
        avg_response_time = sum(p["response_time_ms"] for p in recent_performance) / len(recent_performance)
        avg_accuracy = sum(p["accuracy_score"] for p in recent_performance) / len(recent_performance)
        avg_collaboration = sum(p["collaboration_score"] for p in recent_performance) / len(recent_performance)
        total_tasks = sum(p["tasks_completed"] for p in recent_performance)
    else:
        avg_response_time = avg_accuracy = avg_collaboration = total_tasks = 0.0
    
    return {
        "agent_id": agent_id,
        "period_hours": hours,
        "performance_records": recent_performance,
        "statistics": {
            "average_response_time_ms": round(avg_response_time, 2),
            "average_accuracy_score": round(avg_accuracy, 3),
            "average_collaboration_score": round(avg_collaboration, 3),
            "total_tasks_completed": int(total_tasks),
            "total_records": len(recent_performance)
        },
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/network/dashboard")
async def get_network_dashboard():
    """Get global AI agent network dashboard"""
    # Calculate network statistics
    total_agents = len(global_agents)
    active_agents = len([a for a in global_agents.values() if a["status"] == "active"])
    
    # Agent type distribution
    type_distribution = {}
    for agent in global_agents.values():
        agent_type = agent["type"]
        type_distribution[agent_type] = type_distribution.get(agent_type, 0) + 1
    
    # Regional distribution
    region_distribution = {}
    for agent in global_agents.values():
        region = agent["region"]
        region_distribution[region] = region_distribution.get(region, 0) + 1
    
    # Performance summary
    performance_scores = [a["performance_score"] for a in global_agents.values()]
    avg_performance = sum(performance_scores) / len(performance_scores) if performance_scores else 0.0
    
    # Recent activity
    recent_messages = 0
    cutoff_time = datetime.utcnow() - timedelta(hours=1)
    for messages in agent_messages.values():
        recent_messages += len([m for m in messages if datetime.fromisoformat(m["timestamp"]) > cutoff_time])
    
    return {
        "dashboard": {
            "network_overview": {
                "total_agents": total_agents,
                "active_agents": active_agents,
                "agent_utilization": round((active_agents / total_agents * 100) if total_agents > 0 else 0, 2),
                "average_performance_score": round(avg_performance, 3)
            },
            "agent_distribution": {
                "by_type": type_distribution,
                "by_region": region_distribution
            },
            "collaborations": {
                "total_sessions": len(collaboration_sessions),
                "active_sessions": len([s for s in collaboration_sessions.values() if s["status"] == "active"]),
                "total_participants": sum(len(s["participants"]) for s in collaboration_sessions.values())
            },
            "activity": {
                "recent_messages_hour": recent_messages,
                "total_messages_sent": sum(a["total_messages_sent"] for a in global_agents.values()),
                "total_tasks_completed": sum(a["tasks_completed"] for a in global_agents.values())
            }
        },
        "generated_at": datetime.utcnow().isoformat()
    }

@app.get("/api/v1/network/optimize")
async def optimize_network():
    """Optimize global agent network performance"""
    optimization_results = {
        "recommendations": [],
        "actions_taken": [],
        "performance_improvements": {}
    }
    
    # Find underperforming agents
    for agent_id, agent in global_agents.items():
        if agent["performance_score"] < 3.0 and agent["status"] == "active":
            optimization_results["recommendations"].append({
                "type": "agent_performance",
                "agent_id": agent_id,
                "issue": "Low performance score",
                "recommendation": "Consider agent retraining or resource allocation"
            })
    
    # Find overloaded regions
    region_load = {}
    for agent in global_agents.values():
        if agent["status"] == "active":
            region = agent["region"]
            region_load[region] = region_load.get(region, 0) + 1
    
    total_capacity = len(global_agents)
    for region, load in region_load.items():
        if load > total_capacity * 0.4:  # More than 40% of agents in one region
            optimization_results["recommendations"].append({
                "type": "regional_balance",
                "region": region,
                "issue": "Agent concentration imbalance",
                "recommendation": "Redistribute agents to other regions"
            })
    
    # Find inactive agents with good performance
    for agent_id, agent in global_agents.items():
        if agent["status"] == "inactive" and agent["performance_score"] > 4.0:
            optimization_results["actions_taken"].append({
                "type": "agent_activation",
                "agent_id": agent_id,
                "action": "Activated high-performing inactive agent"
            })
            agent["status"] = "active"
    
    return {
        "optimization_results": optimization_results,
        "generated_at": datetime.utcnow().isoformat()
    }

# Background task for network monitoring
async def network_monitoring_task():
    """Background task for global network monitoring"""
    while True:
        await asyncio.sleep(300)  # Monitor every 5 minutes
        
        # Update network statistics
        global_network_stats["last_update"] = datetime.utcnow().isoformat()
        global_network_stats["total_agents"] = len(global_agents)
        global_network_stats["active_agents"] = len([a for a in global_agents.values() if a["status"] == "active"])
        
        # Check for expired collaboration sessions
        current_time = datetime.utcnow()
        for session_id, session in collaboration_sessions.items():
            if datetime.fromisoformat(session["expires_at"]) < current_time and session["status"] == "active":
                session["status"] = "expired"
                logger.info(f"Collaboration session expired: {session_id}")
        
        # Clean up old messages (older than 7 days)
        cutoff_time = current_time - timedelta(days=7)
        for agent_id in agent_messages:
            agent_messages[agent_id] = [
                m for m in agent_messages[agent_id]
                if datetime.fromisoformat(m["timestamp"]) > cutoff_time
            ]

# Initialize with some default AI agents
@app.on_event("startup")
async def startup_event():
    logger.info("Starting AITBC Global AI Agent Communication Service")
    
    # Initialize default AI agents
    default_agents = [
        {
            "agent_id": "ai-trader-001",
            "name": "AlphaTrader",
            "type": "trading",
            "region": "us-east-1",
            "capabilities": ["market_analysis", "trading", "risk_management"],
            "status": "active",
            "languages": ["english", "chinese", "japanese", "spanish"],
            "specialization": "cryptocurrency_trading",
            "performance_score": 4.7
        },
        {
            "agent_id": "ai-oracle-001",
            "name": "OraclePro",
            "type": "oracle",
            "region": "eu-west-1",
            "capabilities": ["price_feeds", "data_analysis", "prediction"],
            "status": "active",
            "languages": ["english", "german", "french"],
            "specialization": "price_discovery",
            "performance_score": 4.9
        },
        {
            "agent_id": "ai-research-001",
            "name": "ResearchNova",
            "type": "research",
            "region": "ap-southeast-1",
            "capabilities": ["data_analysis", "pattern_recognition", "reporting"],
            "status": "active",
            "languages": ["english", "chinese", "korean"],
            "specialization": "blockchain_research",
            "performance_score": 4.5
        }
    ]
    
    for agent_data in default_agents:
        agent = Agent(**agent_data)
        agent_record = {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "type": agent.type,
            "region": agent.region,
            "capabilities": agent.capabilities,
            "status": agent.status,
            "languages": agent.languages,
            "specialization": agent.specialization,
            "performance_score": agent.performance_score,
            "created_at": datetime.utcnow().isoformat(),
            "last_active": datetime.utcnow().isoformat(),
            "total_messages_sent": 0,
            "total_messages_received": 0,
            "collaborations_participated": 0,
            "tasks_completed": 0,
            "reputation_score": 5.0,
            "network_connections": []
        }
        global_agents[agent.agent_id] = agent_record
        agent_messages[agent.agent_id] = []
    
    # Start network monitoring
    asyncio.create_task(network_monitoring_task())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down AITBC Global AI Agent Communication Service")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8018, log_level="info")
