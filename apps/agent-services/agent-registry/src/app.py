#!/usr/bin/env python3
"""
AITBC Agent Registry Service
Central agent discovery and registration system
"""

import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

# Database path - use DATA_DIR environment variable or fallback to /var/lib/aitbc
DATA_DIR = os.environ.get('DATA_DIR', '/var/lib/aitbc')
DB_PATH = os.path.join(DATA_DIR, 'agent_registry.db')

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown (cleanup if needed)
    pass

app = FastAPI(title="AITBC Agent Registry API", version="1.0.0", lifespan=lifespan)

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
        conn.execute('''
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                capabilities TEXT NOT NULL,
                chain_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

# Models
class Agent(BaseModel):
    id: str
    name: str
    type: str
    capabilities: list[str]
    chain_id: str
    endpoint: str
    metadata: dict[str, Any] | None = {}

class AgentRegistration(BaseModel):
    name: str
    type: str
    capabilities: list[str]
    chain_id: str
    endpoint: str
    metadata: dict[str, Any] | None = {}

# API Endpoints

@app.post("/api/agents/register", response_model=Agent)
async def register_agent(agent: AgentRegistration):
    """Register a new agent"""
    agent_id = str(uuid.uuid4())

    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO agents (id, name, type, capabilities, chain_id, endpoint, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            agent_id, agent.name, agent.type,
            json.dumps(agent.capabilities), agent.chain_id,
            agent.endpoint, json.dumps(agent.metadata)
        ))
        conn.commit()

    return Agent(
        id=agent_id,
        name=agent.name,
        type=agent.type,
        capabilities=agent.capabilities,
        chain_id=agent.chain_id,
        endpoint=agent.endpoint,
        metadata=agent.metadata
    )

@app.get("/api/agents", response_model=list[Agent])
async def list_agents(
    agent_type: str | None = None,
    chain_id: str | None = None,
    capability: str | None = None
):
    """List registered agents with optional filters"""
    with get_db_connection() as conn:
        query = "SELECT * FROM agents WHERE status = 'active'"
        params = []

        if agent_type:
            query += " AND type = ?"
            params.append(agent_type)

        if chain_id:
            query += " AND chain_id = ?"
            params.append(chain_id)

        if capability:
            query += " AND capabilities LIKE ?"
            params.append(f'%{capability}%')

        agents = conn.execute(query, params).fetchall()

        return [
            Agent(
                id=agent["id"],
                name=agent["name"],
                type=agent["type"],
                capabilities=json.loads(agent["capabilities"]),
                chain_id=agent["chain_id"],
                endpoint=agent["endpoint"],
                metadata=json.loads(agent["metadata"] or "{}")
            )
            for agent in agents
        ]

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now(UTC)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8013)
