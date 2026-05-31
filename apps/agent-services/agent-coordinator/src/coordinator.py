#!/usr/bin/env python3
"""
AITBC Agent Coordinator Service
Agent task coordination and management
"""

import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from aitbc import get_logger

logger = get_logger(__name__)

# Use absolute path for database in /var/lib/aitbc for persistence
DB_DIR = "/var/lib/aitbc"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "agent_coordinator.db")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown (cleanup if needed)
    pass

app = FastAPI(title="AITBC Agent Coordinator API", version="1.0.0", lifespan=lifespan)

# Database setup
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db_connection():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()

# Initialize database
def init_db():
    with get_db_connection() as conn:
        # Tasks table (existing)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                required_capabilities TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                assigned_agent_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                result TEXT
            )
        ''')

        # Agents table (new)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                agent_type TEXT NOT NULL,
                status TEXT NOT NULL,
                capabilities TEXT NOT NULL,
                services TEXT NOT NULL,
                endpoints TEXT NOT NULL,
                metadata TEXT,
                last_heartbeat TIMESTAMP,
                registration_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                load_metrics TEXT,
                health_score REAL DEFAULT 1.0
            )
        ''')

        # Agent assignments table (new)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS agent_assignments (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT DEFAULT 'pending',
                response_time REAL,
                success BOOLEAN DEFAULT 0,
                error_message TEXT
            )
        ''')

        # Commit the transaction
        conn.commit()

# Models
class Task(BaseModel):
    id: str
    task_type: str
    payload: dict[str, Any]
    required_capabilities: list[str]
    priority: str
    status: str
    assigned_agent_id: str | None = None

class TaskCreation(BaseModel):
    task_type: str
    payload: dict[str, Any]
    required_capabilities: list[str]
    priority: str = "normal"

class AgentRegistrationRequest(BaseModel):
    agent_id: str
    agent_type: str
    capabilities: list[str]
    services: list[str]
    endpoints: dict[str, str]
    metadata: dict[str, Any] | None = {}

class AgentStatusUpdate(BaseModel):
    status: str
    load_metrics: dict[str, float] | None = {}

# API Endpoints

@app.post("/api/tasks", response_model=Task)
async def create_task(task: TaskCreation):
    """Create a new task and attempt to assign it to an agent"""
    task_id = str(uuid.uuid4())

    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO tasks (id, task_type, payload, required_capabilities, priority, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            task_id, task.task_type, json.dumps(task.payload),
            json.dumps(task.required_capabilities), task.priority, "pending"
        ))

    # Attempt to assign task to an agent
    assigned_agent_id = assign_task_to_agent(task_id, task.required_capabilities)

    if assigned_agent_id:
        logger.info(f"Task {task_id} assigned to agent {assigned_agent_id}")
    else:
        logger.info(f"Task {task_id} - no eligible agents found")

    return Task(
        id=task_id,
        task_type=task.task_type,
        payload=task.payload,
        required_capabilities=task.required_capabilities,
        priority=task.priority,
        status="assigned" if assigned_agent_id else "pending",
        assigned_agent_id=assigned_agent_id
    )

@app.get("/api/tasks", response_model=list[Task])
async def list_tasks(status: str | None = None):
    """List tasks with optional status filter"""
    with get_db_connection() as conn:
        query = "SELECT * FROM tasks"
        params = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        tasks = conn.execute(query, params).fetchall()

        return [
            Task(
                id=task["id"],
                task_type=task["task_type"],
                payload=json.loads(task["payload"]),
                required_capabilities=json.loads(task["required_capabilities"]),
                priority=task["priority"],
                status=task["status"],
                assigned_agent_id=task["assigned_agent_id"]
            )
            for task in tasks
        ]

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now(UTC)}

@app.get("/tasks/status")
async def get_task_status():
    """Get task distribution statistics including active agents"""
    logger.debug(f"DEBUG: Querying tasks/status, DB_PATH={DB_PATH}")
    with get_db_connection() as conn:
        # Get task statistics
        tasks = conn.execute("SELECT * FROM tasks").fetchall()
        tasks_distributed = len([t for t in tasks if t["assigned_agent_id"]])
        tasks_completed = len([t for t in tasks if t["status"] == "completed"])
        tasks_failed = len([t for t in tasks if t["status"] == "failed"])

        # Get active agents count
        agents = conn.execute("SELECT * FROM agents WHERE status = ?", ("active",)).fetchall()
        logger.debug(f"DEBUG: Found {len(agents)} active agents")
        active_agents = len(agents)

        # Calculate load balancer stats
        agent_weights = len(agents)
        total_assignments = len(tasks_distributed)
        successful_assignments = tasks_completed
        failed_assignments = tasks_failed

        # Calculate average agent load
        total_load = 0
        for agent in agents:
            load_metrics = json.loads(agent["load_metrics"]) if agent["load_metrics"] else {}
            total_load += load_metrics.get("active_connections", 0) + load_metrics.get("pending_tasks", 0)
        avg_agent_load = total_load / active_agents if active_agents > 0 else 0

        # Get queue sizes (simulated from pending tasks)
        queue_sizes = {
            "urgent": 0,
            "critical": 0,
            "high": 0,
            "normal": len([t for t in tasks if t["status"] == "pending" and t["priority"] == "normal"]),
            "low": 0
        }

        return {
            "status": "success",
            "stats": {
                "tasks_distributed": tasks_distributed,
                "tasks_completed": tasks_completed,
                "tasks_failed": tasks_failed,
                "avg_distribution_time": 0.0,
                "load_balancer_stats": {
                    "strategy": "least_connections",
                    "total_assignments": total_assignments,
                    "successful_assignments": successful_assignments,
                    "failed_assignments": failed_assignments,
                    "success_rate": successful_assignments / max(1, total_assignments),
                    "active_agents": active_agents,
                    "agent_weights": agent_weights,
                    "avg_agent_load": avg_agent_load
                },
                "queue_sizes": queue_sizes
            },
            "timestamp": datetime.now(UTC).isoformat()
        }

# Agent Management Endpoints

@app.post("/agents/register")
async def register_agent(request: AgentRegistrationRequest):
    """Register a new agent"""
    try:
        logger.debug(f"DEBUG: Attempting to register agent {request.agent_id}")
        logger.debug(f"DEBUG: Database path: {DB_PATH}")
        conn = get_db()
        try:
            logger.debug("DEBUG: Database connection established")
            conn.execute('''
                INSERT INTO agents (id, agent_type, status, capabilities, services, endpoints, metadata, last_heartbeat, health_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                request.agent_id,
                request.agent_type,
                "active",
                json.dumps(request.capabilities),
                json.dumps(request.services),
                json.dumps(request.endpoints),
                json.dumps(request.metadata),
                datetime.now(UTC),
                1.0
            ))
            conn.commit()
            logger.debug(f"DEBUG: Agent {request.agent_id} inserted and committed")
        finally:
            conn.close()

        return {
            "status": "success",
            "message": f"Agent {request.agent_id} registered successfully",
            "agent_id": request.agent_id,
            "registered_at": datetime.now(UTC).isoformat()
        }
    except Exception as e:
        logger.error(f"ERROR: Failed to register agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to register agent: {str(e)}")

@app.post("/agents/discover")
async def discover_agents(query: dict[str, Any]):
    """Discover agents based on criteria"""
    try:
        with get_db_connection() as conn:
            # Build query
            sql = "SELECT * FROM agents WHERE status = ?"
            params = ["active"]

            if "agent_type" in query:
                sql += " AND agent_type = ?"
                params.append(query["agent_type"])

            agents = conn.execute(sql, params).fetchall()

            # Filter by capabilities if specified
            if "capabilities" in query:
                required_capabilities = set(query["capabilities"])
                filtered_agents = []
                for agent in agents:
                    agent_capabilities = set(json.loads(agent["capabilities"]))
                    if required_capabilities.issubset(agent_capabilities):
                        filtered_agents.append(agent)
                agents = filtered_agents

            # Filter by services if specified
            if "services" in query:
                required_services = set(query["services"])
                filtered_agents = []
                for agent in agents:
                    agent_services = set(json.loads(agent["services"]))
                    if required_services.issubset(agent_services):
                        filtered_agents.append(agent)
                agents = filtered_agents

            # Sort by health score (highest first)
            agents = sorted(agents, key=lambda a: a["health_score"], reverse=True)

            return {
                "status": "success",
                "query": query,
                "agents": [
                    {
                        "agent_id": agent["id"],
                        "agent_type": agent["agent_type"],
                        "status": agent["status"],
                        "capabilities": json.loads(agent["capabilities"]),
                        "services": json.loads(agent["services"]),
                        "endpoints": json.loads(agent["endpoints"]),
                        "health_score": agent["health_score"],
                        "last_heartbeat": agent["last_heartbeat"]
                    }
                    for agent in agents
                ],
                "count": len(agents),
                "timestamp": datetime.now(UTC).isoformat()
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error discovering agents: {str(e)}")

@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent information by ID"""
    try:
        with get_db_connection() as conn:
            agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()

            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")

            return {
                "status": "success",
                "agent": {
                    "agent_id": agent["id"],
                    "agent_type": agent["agent_type"],
                    "status": agent["status"],
                    "capabilities": json.loads(agent["capabilities"]),
                    "services": json.loads(agent["services"]),
                    "endpoints": json.loads(agent["endpoints"]),
                    "metadata": json.loads(agent["metadata"]) if agent["metadata"] else {},
                    "last_heartbeat": agent["last_heartbeat"],
                    "registration_time": agent["registration_time"],
                    "health_score": agent["health_score"]
                },
                "timestamp": datetime.now(UTC).isoformat()
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting agent: {str(e)}")

@app.put("/agents/{agent_id}/status")
async def update_agent_status(agent_id: str, request: AgentStatusUpdate):
    """Update agent status"""
    try:
        with get_db_connection() as conn:
            # Update status and heartbeat
            conn.execute('''
                UPDATE agents SET status = ?, last_heartbeat = ?
                WHERE id = ?
            ''', (request.status, datetime.now(UTC), agent_id))

            # Update load metrics if provided
            if request.load_metrics:
                conn.execute('''
                    UPDATE agents SET load_metrics = ?
                    WHERE id = ?
                ''', (json.dumps(request.load_metrics), agent_id))

            return {
                "status": "success",
                "message": f"Agent {agent_id} status updated",
                "agent_id": agent_id,
                "new_status": request.status,
                "updated_at": datetime.now(UTC).isoformat()
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating agent status: {str(e)}")

@app.post("/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str):
    """Agent heartbeat endpoint"""
    try:
        with get_db_connection() as conn:
            conn.execute('''
                UPDATE agents SET last_heartbeat = ?
                WHERE id = ?
            ''', (datetime.now(UTC), agent_id))

            return {
                "status": "success",
                "message": f"Heartbeat received for agent {agent_id}",
                "timestamp": datetime.now(UTC).isoformat()
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating heartbeat: {str(e)}")

# Agent Matching and Task Distribution

def find_eligible_agents(required_capabilities: list[str], agent_type: str | None = None) -> list[dict[str, Any]]:
    """Find eligible agents for task"""
    with get_db_connection() as conn:
        # Build query
        sql = "SELECT * FROM agents WHERE status = ?"
        params = ["active"]

        if agent_type:
            sql += " AND agent_type = ?"
            params.append(agent_type)

        agents = conn.execute(sql, params).fetchall()

        # Filter by capabilities
        if required_capabilities:
            required_set = set(required_capabilities)
            eligible_agents = []
            for agent in agents:
                agent_capabilities = set(json.loads(agent["capabilities"]))
                if required_set.issubset(agent_capabilities):
                    eligible_agents.append(agent)
            agents = eligible_agents

        # Sort by health score (highest first)
        agents = sorted(agents, key=lambda a: a["health_score"], reverse=True)

        return [
            {
                "agent_id": agent["id"],
                "agent_type": agent["agent_type"],
                "health_score": agent["health_score"],
                "load_metrics": json.loads(agent["load_metrics"]) if agent["load_metrics"] else {}
            }
            for agent in agents
        ]

def assign_task_to_agent(task_id: str, required_capabilities: list[str], agent_type: str | None = None) -> str | None:
    """Assign task to best available agent using least_connections strategy"""
    # Find eligible agents
    eligible_agents = find_eligible_agents(required_capabilities, agent_type)

    if not eligible_agents:
        return None

    # Select agent with least connections (load balancing)
    selected_agent = min(eligible_agents, key=lambda a: a["load_metrics"].get("active_connections", 0))

    # Record assignment
    assignment_id = str(uuid.uuid4())
    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO agent_assignments (id, task_id, agent_id, status)
            VALUES (?, ?, ?, ?)
        ''', (assignment_id, task_id, selected_agent["agent_id"], "assigned"))

        # Update task with assigned agent
        conn.execute('''
            UPDATE tasks SET assigned_agent_id = ?, status = ?
            WHERE id = ?
        ''', (selected_agent["agent_id"], "assigned", task_id))

        # Update agent load metrics
        load_metrics = selected_agent["load_metrics"]
        load_metrics["active_connections"] = load_metrics.get("active_connections", 0) + 1
        load_metrics["pending_tasks"] = load_metrics.get("pending_tasks", 0) + 1
        conn.execute('''
            UPDATE agents SET load_metrics = ?
            WHERE id = ?
        ''', (json.dumps(load_metrics), selected_agent["agent_id"]))

    return selected_agent["agent_id"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8012)
