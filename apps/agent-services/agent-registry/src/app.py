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

from fastapi import FastAPI, Request
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

@app.get("/agent/health")
async def agent_health():
    """Agent health endpoint for nginx proxy"""
    return {"status": "ok", "timestamp": datetime.now(UTC)}

@app.get("/agent/discovery.json")
async def agent_discovery():
    """Agent discovery endpoint for nginx proxy"""
    with get_db_connection() as conn:
        agents = conn.execute("SELECT * FROM agents WHERE status = 'active'").fetchall()

        return {
            "agents": [
                {
                    "id": agent["id"],
                    "name": agent["name"],
                    "type": agent["type"],
                    "capabilities": json.loads(agent["capabilities"]),
                    "chain_id": agent["chain_id"],
                    "endpoint": agent["endpoint"],
                    "status": agent["status"],
                    "last_heartbeat": agent["last_heartbeat"]
                }
                for agent in agents
            ],
            "count": len(agents),
            "timestamp": datetime.now(UTC).isoformat()
        }

@app.get("/agent/islands.json")
async def agent_islands():
    """Agent islands endpoint for nginx proxy"""
    # Return blockchain chain info from environment
    chain_id = os.environ.get("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
    supported_chains = os.environ.get("SUPPORTED_CHAINS", "ait-hub.aitbc.bubuit.net").split(",")
    return {
        "islands": supported_chains,
        "count": len(supported_chains)
    }

@app.get("/agent/chains.json")
async def agent_chains():
    """Agent chains endpoint for nginx proxy"""
    # Return blockchain chain info from environment
    chain_id = os.environ.get("CHAIN_ID", "ait-hub.aitbc.bubuit.net")
    supported_chains = os.environ.get("SUPPORTED_CHAINS", "ait-hub.aitbc.bubuit.net").split(",")
    return {
        "chains": supported_chains,
        "count": len(supported_chains)
    }

@app.get("/agent/openapi.json")
async def agent_openapi(request: Request):
    """OpenAPI specification for agent registry API"""
    import socket

    # Get hostname from environment or system
    hostname = os.getenv("AITBC_HOSTNAME", socket.gethostname())

    # Detect protocol from request or environment
    protocol = os.getenv("AITBC_PROTOCOL", "http")
    if hasattr(request, 'url') and request.url:
        protocol = request.url.scheme

    base_url = f"{protocol}://{hostname}"

    # Get contact email from node.env
    contact_email = os.getenv("CONTACT_EMAIL", "andreas.fleckl@bubuit.net")

    return {
        "openapi": "3.0.0",
        "info": {
            "title": "AITBC Agent Registry API",
            "version": "1.0.0",
            "description": "Agent discovery and registration system for AITBC network",
            "contact": {
                "name": "AITBC Network",
                "email": contact_email
            }
        },
        "servers": [
            {"url": base_url, "description": "AITBC Hub Node"}
        ],
        "paths": {
            "/api/agents/register": {
                "post": {
                    "summary": "Register a new agent",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "type": {"type": "string"},
                                        "capabilities": {"type": "array", "items": {"type": "string"}},
                                        "chain_id": {"type": "string"},
                                        "endpoint": {"type": "string"},
                                        "metadata": {"type": "object"}
                                    },
                                    "required": ["name", "type", "capabilities", "chain_id", "endpoint"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {"description": "Agent registered successfully"}
                    }
                }
            },
            "/api/agents": {
                "get": {
                    "summary": "List registered agents",
                    "parameters": [
                        {"name": "agent_type", "in": "query", "schema": {"type": "string"}},
                        {"name": "chain_id", "in": "query", "schema": {"type": "string"}},
                        {"name": "capability", "in": "query", "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {"description": "List of agents"}
                    }
                }
            },
            "/agent/health": {
                "get": {
                    "summary": "Health check",
                    "responses": {
                        "200": {"description": "Service is healthy"}
                    }
                }
            },
            "/agent/discovery.json": {
                "get": {
                    "summary": "Agent discovery",
                    "responses": {
                        "200": {"description": "List of all registered agents"}
                    }
                }
            },
            "/agent/islands.json": {
                "get": {
                    "summary": "List islands",
                    "responses": {
                        "200": {"description": "List of islands with registered agents"}
                    }
                }
            },
            "/agent/chains.json": {
                "get": {
                    "summary": "List chains",
                    "responses": {
                        "200": {"description": "List of supported chains"}
                    }
                }
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8204)
