"""Agent Management Routers"""

from .agent_creativity import router as agent_creativity_router
from .agent_integration_router import router as agent_integration_router
from .agent_performance import router as agent_performance_router
from .agent_router import router as agent_router
from .agent_security_router import router as agent_security_router
from .services import router as services_router

__all__ = [
    "agent_router",
    "agent_integration_router",
    "agent_performance_router",
    "agent_creativity_router",
    "agent_security_router",
    "services_router",
]
