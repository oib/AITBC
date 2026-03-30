#!/usr/bin/env python3
"""
AITBC Agent Coordinator Service
Agent task coordination and management
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import uuid
from datetime import datetime
import sqlite3
from contextlib import contextmanager

app = FastAPI(title="AITBC Agent Coordinator API", version="1.0.0")

# Database setup
def get_db():
    conn = sqlite3.connect('agent_coordinator.db')
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

# Models
class Task(BaseModel):
    id: str
    task_type: str
    payload: Dict[str, Any]
    required_capabilities: List[str]
    priority: str
    status: str
    assigned_agent_id: Optional[str] = None

class TaskCreation(BaseModel):
    task_type: str
    payload: Dict[str, Any]
    required_capabilities: List[str]
    priority: str = "normal"

# API Endpoints
@app.on_event("startup")
async def startup_event():
    init_db()

@app.post("/api/tasks", response_model=Task)
async def create_task(task: TaskCreation):
    """Create a new task"""
    task_id = str(uuid.uuid4())
    
    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO tasks (id, task_type, payload, required_capabilities, priority, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            task_id, task.task_type, json.dumps(task.payload),
            json.dumps(task.required_capabilities), task.priority, "pending"
        ))
    
    return Task(
        id=task_id,
        task_type=task.task_type,
        payload=task.payload,
        required_capabilities=task.required_capabilities,
        priority=task.priority,
        status="pending"
    )

@app.get("/api/tasks", response_model=List[Task])
async def list_tasks(status: Optional[str] = None):
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
    return {"status": "ok", "timestamp": datetime.utcnow()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8012)
