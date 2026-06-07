from . import agents, ai, alerts, auth, consensus, health, messages, monitor, monitoring, swarm, tasks, users
from . import workflow, websocket

ROUTERS = [
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
    workflow.router,
    websocket.router,
]
