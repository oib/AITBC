#!/usr/bin/env python3
import re

filepath = "/opt/aitbc/apps/agent-management/src/app/services/agent_orchestrator.py"
with open(filepath, "r") as f:
    content = f.read()

replacements = [
    ("    async def initialize(self):", "    async def initialize(self) -> None:"),
    ("    async def register_agent(self, capability: AgentCapability):", "    async def register_agent(self, capability: AgentCapability) -> None:"),
    ("    async def update_agent_status(self, agent_id: str, status: AgentStatus):", "    async def update_agent_status(self, agent_id: str, status: AgentStatus) -> None:"),
    ("    async def _execute_assignments(self, plan: OrchestrationPlan):", "    async def _execute_assignments(self, plan: OrchestrationPlan) -> None:"),
    ("    async def _assign_sub_task(self, sub_task_id: str, plan: OrchestrationPlan):", "    async def _assign_sub_task(self, sub_task_id: str, plan: OrchestrationPlan) -> None:"),
    ("    async def _allocate_resources(self, agent_id: str, sub_task_id: str, requirements):", "    async def _allocate_resources(self, agent_id: str, sub_task_id: str, requirements: Any) -> None:"),
    ("    async def _release_agent_resources(self, agent_id: str, sub_task_id: str):", "    async def _release_agent_resources(self, agent_id: str, sub_task_id: str) -> None:"),
    ("    async def _monitor_executions(self):", "    async def _monitor_executions(self) -> None:"),
    ("    async def _update_agent_status(self):", "    async def _update_agent_status(self) -> None:"),
    ("    async def _update_resource_utilization(self):", "    async def _update_resource_utilization(self) -> None:"),
    ("    async def _load_agent_capabilities(self):", "    async def _load_agent_capabilities(self) -> None:"),
]

for old, new in replacements:
    content = content.replace(old, new)

with open(filepath, "w") as f:
    f.write(content)
print("Fixed agent_orchestrator.py")
