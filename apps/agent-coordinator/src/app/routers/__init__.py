from . import agents, ai, alerts, auth, consensus, health, messages, monitoring, tasks, users

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
]
