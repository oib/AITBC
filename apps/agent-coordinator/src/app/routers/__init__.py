from . import agents, ai, alerts, auth, consensus, health, messages, monitor, monitoring, swarm, tasks, users
from . import agent_messaging, workflow, websocket

ROUTERS = [
    health.router,
    agents.router,
    tasks.router,
    messages.router,
    ai.router,
    consensus.router,
    auth.router,
    users.router,
    monitoring.router,
    alerts.router,
    swarm.router,
    monitor.router,
    agent_messaging.router,
    workflow.router,
    websocket.router,
]
