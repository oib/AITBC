"""
Simple test agent endpoint to verify task distribution
Listens on port 9997 and accepts task execution requests
"""

from datetime import UTC, datetime
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Test Agent Endpoint")


class TaskMessage(BaseModel):
    """Task message structure"""

    id: str
    sender_id: str
    receiver_id: str | None
    message_type: str
    priority: str
    timestamp: str
    payload: dict[str, Any]
    correlation_id: str | None
    reply_to: str | None
    ttl: int


class TaskResponse(BaseModel):
    """Task execution response"""

    status: str
    task_id: str
    agent_id: str
    executed_at: str
    result: dict[str, Any]


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "running", "agent_id": "test-agent-9997", "timestamp": datetime.now(UTC).isoformat()}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "agent_id": "test-agent-9997"}


@app.post("/tasks/execute")
async def execute_task(task: TaskMessage):
    """Execute a task sent by the task distributor"""
    try:
        print(f"[{datetime.now(UTC)}] Received task:")
        print(f"  Task ID: {task.id}")
        print(f"  From: {task.sender_id}")
        print(f"  Type: {task.message_type}")
        print(f"  Priority: {task.priority}")
        print(f"  Payload: {task.payload}")

        # Simulate task processing
        task_data = task.payload.get("task_data", {})
        task_type = task_data.get("task_type", "unknown")

        # Simple task simulation
        result = {"status": "completed", "output": f"Task {task_type} executed successfully", "processing_time_ms": 100}

        response = TaskResponse(
            status="success",
            task_id=task.id,
            agent_id="test-agent-9997",
            executed_at=datetime.now(UTC).isoformat(),
            result=result,
        )

        print(f"[{datetime.now(UTC)}] Task executed successfully")
        return response

    except Exception as e:
        print(f"[{datetime.now(UTC)}] Error executing task: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    print("Starting test agent endpoint on port 9997...")
    uvicorn.run(app, host="0.0.0.0", port=9997, log_level="info")
