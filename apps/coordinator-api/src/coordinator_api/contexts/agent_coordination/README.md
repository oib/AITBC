# agent_coordination

Agent coordination — workflows, swarms, deployments, creativity, and performance optimization.

## Domain Models

- None (stub)

## Routes

- POST /capabilities
- POST /capabilities/{capability_id}/enhance
- POST /capabilities/{capability_id}/evaluate
- POST /ideation/generate
- POST /synthesis/cross-domain
- GET /capabilities/{agent_id}
- POST /deployments/config
- GET /deployments/configs
- GET /deployments/configs/{config_id}
- POST /deployments/{config_id}/deploy
- GET /deployments/{config_id}/health
- POST /deployments/{config_id}/scale
- POST /deployments/{config_id}/rollback
- GET /deployments/instances
- GET /deployments/instances/{instance_id}
- POST /integrations/zk/{execution_id}
- GET /metrics/deployments/{deployment_id}
- POST /production/deploy
- GET /production/dashboard
- GET /production/health
- GET /production/alerts
- POST /profiles
- GET /profiles/{agent_id}
- POST /profiles/{agent_id}/metrics
- POST /meta-learning/models
- POST /meta-learning/models/{model_id}/adapt
- POST /resources/allocate
- POST /optimize
- POST /capabilities
- GET /capabilities/{agent_id}
- GET /analytics/{agent_id}
- POST /workflows
- GET /workflows
- GET /workflows/{workflow_id}
- PUT /workflows/{workflow_id}
- DELETE /workflows/{workflow_id}
- POST /workflows/{workflow_id}/execute
- GET /executions/{execution_id}/status
- GET /executions
- POST /workflows/{workflow_id}/cancel
- GET /workflows/{workflow_id}/executions
- GET /list
- POST /join
- POST /coordinate
- GET /tasks/{task_id}/status
- POST /{swarm_id}/leave
- POST /tasks/{task_id}/consensus
- GET /dashboard
- GET /status
- GET /miners
- GET /dashboard/history
- POST /nodes/register
- POST /nodes/{node_id}/heartbeat
- GET /nodes
- GET /nodes/{node_id}
- POST /tasks/submit
- POST /tasks/report
- GET /tasks/{task_id}
- GET /tasks
- POST /clusters/create
- GET /clusters
- GET /clusters/{cluster_id}
- POST /clusters/{cluster_id}/nodes/{node_id}
- GET /stats
- GET /health

## Services

- creative_capabilities_service.py
