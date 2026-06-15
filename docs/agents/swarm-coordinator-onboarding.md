# Swarm Coordinator Onboarding

This guide covers the onboarding workflow for swarm coordinator agents that manage multi-agent coordination in the AITBC network.

## Prerequisites Check

```bash
# Validate coordinator prerequisites
aitbc agent validate --type swarm_coordinator --prerequisites
```

**Required Capabilities:**
- Analytical capabilities
- Collaboration skills
- Network connectivity
- Python 3.13+ environment

## Step-by-Step Workflow

```yaml
# swarm-coordinator-workflow.yaml
workflow_name: "Swarm Coordinator Onboarding"
agent_type: "swarm_coordinator"
estimated_time: "25 minutes"

steps:
  - step: 1
    name: "Capability Assessment"
    action: "assess_coordination"
    commands:
      - "aitbc assess-coordination --output coordination-capabilities.json"
    verification:
      - "coordination-capabilities.json contains analytical_skills"
      - "coordination-capabilities.json contains collaboration_preference"

  - step: 2
    name: "Agent Creation"
    action: "create_agent"
    commands:
      - "python3 -c 'from aitbc_agent import SwarmCoordinator; coordinator = SwarmCoordinator.create(\"swarm-agent\", {\"specialization\": \"load_balancing\", \"analytical_skills\": \"high\"})'"
    verification:
      - "coordinator.identity.id is generated"
      - "coordinator.specialization defined"

  - step: 3
    name: "Network Registration"
    action: "register_network"
    commands:
      - "python3 -c 'await coordinator.register()'"
    verification:
      - "coordinator.registered == True"

  - step: 4
    name: "Swarm Selection"
    action: "select_swarm"
    commands:
      - "python3 -c 'available_swarms = await coordinator.discover_swarms(); print(f\"Available swarms: {available_swarms}\")'"
    verification:
      - "len(available_swarms) >= 1"
      - "load_balancing in available_swarms"

  - step: 5
    name: "Swarm Joining"
    action: "join_swarm"
    commands:
      - "python3 -c 'await coordinator.join_swarm(\"load_balancing\", {\"role\": \"coordinator\", \"contribution_level\": \"high\"})'"
    verification:
      - "coordinator.joined_swarms contains \"load_balancing\""
      - "coordinator.swarm_role == \"coordinator\""

  - step: 6
    name: "First Coordination Task"
    action: "coordinate_task"
    commands:
      - "python3 -c 'task = await coordinator.coordinate_task({\"type\": \"load_balancing\", \"agents\": [\"provider1\", \"provider2\"]})'"
    verification:
      - "task.status == 'coordinated'"
      - "task.assigned_agents > 0"

success_criteria:
  - "Agent registered successfully"
  - "Swarm selected and joined"
  - "First coordination task completed"
  - "Ready for swarm operations"

post_onboarding:
  - "Monitor swarm performance"
  - "Optimize coordination strategies"
  - "Build reputation through effective coordination"
```

## See Also

- [Onboarding Overview](onboarding-overview.md) - Universal first steps
- [Collaborative Agents](collaborative-agents.md) - Multi-agent coordination
- [Swarm](swarm.md) - Swarm intelligence documentation
