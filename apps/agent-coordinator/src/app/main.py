"""
Main FastAPI Application for AITBC Agent Coordinator
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional, Any
import uuid

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
import uvicorn
import time

from .protocols.communication import CommunicationManager, create_protocol, MessageType
from .protocols.message_types import MessageProcessor, create_task_message, create_status_message
from .routing.agent_discovery import AgentRegistry, AgentDiscoveryService, create_agent_info
from .routing.load_balancer import LoadBalancer, TaskDistributor, TaskPriority, LoadBalancingStrategy
from .ai.realtime_learning import learning_system
from .ai.advanced_ai import ai_integration
from .consensus.distributed_consensus import distributed_consensus
from .auth.jwt_handler import jwt_handler, password_manager, api_key_manager
from .auth.middleware import get_current_user, require_permissions, require_role, security_headers
from .auth.permissions import permission_manager, Permission, Role
from .monitoring.prometheus_metrics import metrics_registry, performance_monitor
from .monitoring.alerting import alert_manager, SLAMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global variables
agent_registry: Optional[AgentRegistry] = None
discovery_service: Optional[AgentDiscoveryService] = None
load_balancer: Optional[LoadBalancer] = None
task_distributor: Optional[TaskDistributor] = None
communication_manager: Optional[CommunicationManager] = None
message_processor: Optional[MessageProcessor] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting AITBC Agent Coordinator...")
    
    # Initialize services
    global agent_registry, discovery_service, load_balancer, task_distributor, communication_manager, message_processor
    
    # Start agent registry
    agent_registry = AgentRegistry()
    await agent_registry.start()
    
    # Initialize discovery service
    discovery_service = AgentDiscoveryService(agent_registry)
    
    # Initialize load balancer
    load_balancer = LoadBalancer(agent_registry)
    load_balancer.set_strategy(LoadBalancingStrategy.LEAST_CONNECTIONS)
    
    # Initialize task distributor
    task_distributor = TaskDistributor(load_balancer)
    
    # Initialize communication manager
    communication_manager = CommunicationManager("agent-coordinator")
    
    # Initialize message processor
    message_processor = MessageProcessor("agent-coordinator")
    
    # Start background tasks
    asyncio.create_task(task_distributor.start_distribution())
    asyncio.create_task(message_processor.start_processing())
    
    logger.info("Agent Coordinator started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down AITBC Agent Coordinator...")
    
    if agent_registry:
        await agent_registry.stop()
    
    logger.info("Agent Coordinator shut down")

# Create FastAPI app
app = FastAPI(
    title="AITBC Agent Coordinator",
    description="Advanced multi-agent coordination and management system",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class AgentRegistrationRequest(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(..., description="Type of agent")
    capabilities: List[str] = Field(default_factory=list, description="Agent capabilities")
    services: List[str] = Field(default_factory=list, description="Available services")
    endpoints: Dict[str, str] = Field(default_factory=dict, description="Service endpoints")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

class AgentStatusUpdate(BaseModel):
    status: str = Field(..., description="Agent status")
    load_metrics: Dict[str, float] = Field(default_factory=dict, description="Load metrics")

class TaskSubmission(BaseModel):
    task_data: Dict[str, Any] = Field(..., description="Task data")
    priority: str = Field("normal", description="Task priority")
    requirements: Optional[Dict[str, Any]] = Field(None, description="Task requirements")

class MessageRequest(BaseModel):
    receiver_id: str = Field(..., description="Receiver agent ID")
    message_type: str = Field(..., description="Message type")
    payload: Dict[str, Any] = Field(..., description="Message payload")
    priority: str = Field("normal", description="Message priority")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "agent-coordinator",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "AITBC Agent Coordinator",
        "description": "Advanced multi-agent coordination and management system",
        "version": "1.0.0",
        "endpoints": [
            "/health",
            "/agents/register",
            "/agents/discover",
            "/agents/{agent_id}",
            "/agents/{agent_id}/status",
            "/tasks/submit",
            "/tasks/status",
            "/messages/send",
            "/load-balancer/stats",
            "/registry/stats"
        ]
    }

# Agent registration
@app.post("/agents/register")
async def register_agent(request: AgentRegistrationRequest):
    """Register a new agent"""
    try:
        if not agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        # Create agent info with validation
        try:
            agent_info = create_agent_info(
                agent_id=request.agent_id,
                agent_type=request.agent_type,
                capabilities=request.capabilities,
                services=request.services,
                endpoints=request.endpoints
            )
            agent_info.metadata = request.metadata
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        
        # Register agent
        success = await agent_registry.register_agent(agent_info)
        
        if success:
            return {
                "status": "success",
                "message": f"Agent {request.agent_id} registered successfully",
                "agent_id": request.agent_id,
                "registered_at": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to register agent")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Agent discovery
@app.post("/agents/discover")
async def discover_agents(query: Dict[str, Any]):
    """Discover agents based on criteria"""
    try:
        if not agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        agents = await agent_registry.discover_agents(query)
        
        return {
            "status": "success",
            "query": query,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error discovering agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get agent by ID
@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent information by ID"""
    try:
        if not agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        agent = await agent_registry.get_agent_by_id(agent_id)
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        return {
            "status": "success",
            "agent": agent.to_dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Update agent status
@app.put("/agents/{agent_id}/status")
async def update_agent_status(agent_id: str, request: AgentStatusUpdate):
    """Update agent status"""
    try:
        if not agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        from .routing.agent_discovery import AgentStatus
        
        success = await agent_registry.update_agent_status(
            agent_id,
            AgentStatus(request.status),
            request.load_metrics
        )
        
        if success:
            return {
                "status": "success",
                "message": f"Agent {agent_id} status updated",
                "agent_id": agent_id,
                "new_status": request.status,
                "updated_at": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update agent status")
            
    except Exception as e:
        logger.error(f"Error updating agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Submit task
@app.post("/tasks/submit")
async def submit_task(request: TaskSubmission, background_tasks: BackgroundTasks):
    """Submit a task for distribution"""
    try:
        if not task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        
        # Convert priority string to enum
        try:
            priority = TaskPriority(request.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}")
        
        # Submit task
        await task_distributor.submit_task(
            request.task_data,
            priority,
            request.requirements
        )
        
        return {
            "status": "success",
            "message": "Task submitted successfully",
            "task_id": request.task_data.get("task_id", str(uuid.uuid4())),
            "priority": request.priority,
            "submitted_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get task status
@app.get("/tasks/status")
async def get_task_status():
    """Get task distribution statistics"""
    try:
        if not task_distributor:
            raise HTTPException(status_code=503, detail="Task distributor not available")
        
        stats = task_distributor.get_distribution_stats()
        
        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Send message
@app.post("/messages/send")
async def send_message(request: MessageRequest):
    """Send message to agent"""
    try:
        if not communication_manager:
            raise HTTPException(status_code=503, detail="Communication manager not available")
        
        from .protocols.communication import AgentMessage, Priority
        
        # Convert message type
        try:
            message_type = MessageType(request.message_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid message type: {request.message_type}")
        
        # Convert priority
        try:
            priority = Priority(request.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {request.priority}")
        
        # Create message
        message = AgentMessage(
            sender_id="agent-coordinator",
            receiver_id=request.receiver_id,
            message_type=message_type,
            priority=priority,
            payload=request.payload
        )
        
        # Send message
        success = await communication_manager.send_message("hierarchical", message)
        
        if success:
            return {
                "status": "success",
                "message": "Message sent successfully",
                "message_id": message.id,
                "receiver_id": request.receiver_id,
                "sent_at": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send message")
            
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Load balancer statistics
@app.get("/load-balancer/stats")
async def get_load_balancer_stats():
    """Get load balancer statistics"""
    try:
        if not load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")
        
        stats = load_balancer.get_load_balancing_stats()
        
        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting load balancer stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Registry statistics
@app.get("/registry/stats")
async def get_registry_stats():
    """Get agent registry statistics"""
    try:
        if not agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        stats = await agent_registry.get_registry_stats()
        
        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting registry stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get agents by service
@app.get("/agents/service/{service}")
async def get_agents_by_service(service: str):
    """Get agents that provide a specific service"""
    try:
        if not agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        agents = await agent_registry.get_agents_by_service(service)
        
        return {
            "status": "success",
            "service": service,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting agents by service: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get agents by capability
@app.get("/agents/capability/{capability}")
async def get_agents_by_capability(capability: str):
    """Get agents that have a specific capability"""
    try:
        if not agent_registry:
            raise HTTPException(status_code=503, detail="Agent registry not available")
        
        agents = await agent_registry.get_agents_by_capability(capability)
        
        return {
            "status": "success",
            "capability": capability,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting agents by capability: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Set load balancing strategy
@app.put("/load-balancer/strategy")
async def set_load_balancing_strategy(strategy: str = Query(..., description="Load balancing strategy")):
    """Set load balancing strategy"""
    try:
        if not load_balancer:
            raise HTTPException(status_code=503, detail="Load balancer not available")
        
        try:
            load_balancing_strategy = LoadBalancingStrategy(strategy.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid strategy: {strategy}")
        
        load_balancer.set_strategy(load_balancing_strategy)
        
        return {
            "status": "success",
            "message": f"Load balancing strategy set to {strategy}",
            "strategy": strategy,
            "updated_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting load balancing strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Advanced AI/ML endpoints
@app.post("/ai/learning/experience")
async def record_learning_experience(experience_data: Dict[str, Any]):
    """Record a learning experience for the AI system"""
    try:
        result = await learning_system.record_experience(experience_data)
        return result
    except Exception as e:
        logger.error(f"Error recording learning experience: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/learning/statistics")
async def get_learning_statistics():
    """Get learning system statistics"""
    try:
        result = await learning_system.get_learning_statistics()
        return result
    except Exception as e:
        logger.error(f"Error getting learning statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/learning/predict")
async def predict_performance(context: Dict[str, Any], action: str = Query(...)):
    """Predict performance for a given action"""
    try:
        result = await learning_system.predict_performance(context, action)
        return result
    except Exception as e:
        logger.error(f"Error predicting performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/learning/recommend")
async def recommend_action(context: Dict[str, Any], available_actions: List[str]):
    """Get AI-recommended action"""
    try:
        result = await learning_system.recommend_action(context, available_actions)
        return result
    except Exception as e:
        logger.error(f"Error recommending action: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/neural-network/create")
async def create_neural_network(config: Dict[str, Any]):
    """Create a new neural network"""
    try:
        result = await ai_integration.create_neural_network(config)
        return result
    except Exception as e:
        logger.error(f"Error creating neural network: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/neural-network/{network_id}/train")
async def train_neural_network(network_id: str, training_data: List[Dict[str, Any]], epochs: int = 100):
    """Train a neural network"""
    try:
        result = await ai_integration.train_neural_network(network_id, training_data, epochs)
        return result
    except Exception as e:
        logger.error(f"Error training neural network: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/neural-network/{network_id}/predict")
async def predict_with_neural_network(network_id: str, features: List[float]):
    """Make prediction with neural network"""
    try:
        result = await ai_integration.predict_with_neural_network(network_id, features)
        return result
    except Exception as e:
        logger.error(f"Error predicting with neural network: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/ml-model/create")
async def create_ml_model(config: Dict[str, Any]):
    """Create a new ML model"""
    try:
        result = await ai_integration.create_ml_model(config)
        return result
    except Exception as e:
        logger.error(f"Error creating ML model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/ml-model/{model_id}/train")
async def train_ml_model(model_id: str, training_data: List[Dict[str, Any]]):
    """Train an ML model"""
    try:
        result = await ai_integration.train_ml_model(model_id, training_data)
        return result
    except Exception as e:
        logger.error(f"Error training ML model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/ml-model/{model_id}/predict")
async def predict_with_ml_model(model_id: str, features: List[float]):
    """Make prediction with ML model"""
    try:
        result = await ai_integration.predict_with_ml_model(model_id, features)
        return result
    except Exception as e:
        logger.error(f"Error predicting with ML model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/statistics")
async def get_ai_statistics():
    """Get comprehensive AI/ML statistics"""
    try:
        result = await ai_integration.get_ai_statistics()
        return result
    except Exception as e:
        logger.error(f"Error getting AI statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Distributed consensus endpoints
@app.post("/consensus/node/register")
async def register_consensus_node(node_data: Dict[str, Any]):
    """Register a node in the consensus network"""
    try:
        result = await distributed_consensus.register_node(node_data)
        return result
    except Exception as e:
        logger.error(f"Error registering consensus node: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/consensus/proposal/create")
async def create_consensus_proposal(proposal_data: Dict[str, Any]):
    """Create a new consensus proposal"""
    try:
        result = await distributed_consensus.create_proposal(proposal_data)
        return result
    except Exception as e:
        logger.error(f"Error creating consensus proposal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/consensus/proposal/{proposal_id}/vote")
async def cast_consensus_vote(proposal_id: str, node_id: str, vote: bool):
    """Cast a vote for a proposal"""
    try:
        result = await distributed_consensus.cast_vote(proposal_id, node_id, vote)
        return result
    except Exception as e:
        logger.error(f"Error casting consensus vote: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/consensus/proposal/{proposal_id}")
async def get_proposal_status(proposal_id: str):
    """Get proposal status"""
    try:
        result = await distributed_consensus.get_proposal_status(proposal_id)
        return result
    except Exception as e:
        logger.error(f"Error getting proposal status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/consensus/algorithm")
async def set_consensus_algorithm(algorithm: str = Query(..., description="Consensus algorithm")):
    """Set the consensus algorithm"""
    try:
        result = await distributed_consensus.set_consensus_algorithm(algorithm)
        return result
    except Exception as e:
        logger.error(f"Error setting consensus algorithm: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/consensus/statistics")
async def get_consensus_statistics():
    """Get consensus statistics"""
    try:
        result = await distributed_consensus.get_consensus_statistics()
        return result
    except Exception as e:
        logger.error(f"Error getting consensus statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/consensus/node/{node_id}/status")
async def update_node_status(node_id: str, is_active: bool):
    """Update node status"""
    try:
        result = await distributed_consensus.update_node_status(node_id, is_active)
        return result
    except Exception as e:
        logger.error(f"Error updating node status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Advanced features status endpoint
@app.get("/advanced-features/status")
async def get_advanced_features_status():
    """Get status of all advanced features"""
    try:
        learning_stats = await learning_system.get_learning_statistics()
        ai_stats = await ai_integration.get_ai_statistics()
        consensus_stats = await distributed_consensus.get_consensus_statistics()
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "features": {
                "realtime_learning": {
                    "status": "active",
                    "experiences": learning_stats.get("total_experiences", 0),
                    "learning_rate": learning_stats.get("learning_rate", 0.01),
                    "models": learning_stats.get("models_count", 0)
                },
                "advanced_ai": {
                    "status": "active",
                    "models": ai_stats.get("total_models", 0),
                    "neural_networks": ai_stats.get("total_neural_networks", 0),
                    "predictions": ai_stats.get("total_predictions", 0)
                },
                "distributed_consensus": {
                    "status": "active",
                    "nodes": consensus_stats.get("active_nodes", 0),
                    "proposals": consensus_stats.get("total_proposals", 0),
                    "success_rate": consensus_stats.get("success_rate", 0.0),
                    "algorithm": consensus_stats.get("current_algorithm", "majority_vote")
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting advanced features status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Authentication endpoints
@app.post("/auth/login")
async def login(login_data: Dict[str, str]):
    """User login with username and password"""
    try:
        username = login_data.get("username")
        password = login_data.get("password")
        
        if not username or not password:
            raise HTTPException(status_code=422, detail="Username and password are required")
        
        # In a real implementation, verify credentials against database
        # For demo, we'll create a simple user
        if username == "admin" and password == "admin123":
            user_id = "admin_001"
            role = Role.ADMIN
        elif username == "operator" and password == "operator123":
            user_id = "operator_001"
            role = Role.OPERATOR
        elif username == "user" and password == "user123":
            user_id = "user_001"
            role = Role.USER
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Assign role to user
        permission_manager.assign_role(user_id, role)
        
        # Generate JWT token
        token_result = jwt_handler.generate_token({
            "user_id": user_id,
            "username": username,
            "role": role.value,
            "permissions": [perm.value for perm in permission_manager.user_permissions.get(user_id, set())]
        })
        
        # Generate refresh token
        refresh_result = jwt_handler.generate_refresh_token({
            "user_id": user_id,
            "username": username,
            "role": role.value
        })
        
        return {
            "status": "success",
            "user_id": user_id,
            "username": username,
            "role": role.value,
            "access_token": token_result["token"],
            "refresh_token": refresh_result["refresh_token"],
            "expires_at": token_result["expires_at"],
            "token_type": token_result["token_type"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/refresh")
async def refresh_token(refresh_data: Dict[str, str]):
    """Refresh access token using refresh token"""
    try:
        refresh_token = refresh_data.get("refresh_token")
        
        if not refresh_token:
            raise HTTPException(status_code=422, detail="Refresh token is required")
        
        result = jwt_handler.refresh_access_token(refresh_token)
        
        if result["status"] == "error":
            raise HTTPException(status_code=401, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/validate")
async def validate_token(validate_data: Dict[str, str]):
    """Validate JWT token"""
    try:
        token = validate_data.get("token")
        
        if not token:
            raise HTTPException(status_code=422, detail="Token is required")
        
        result = jwt_handler.validate_token(token)
        
        if not result["valid"]:
            raise HTTPException(status_code=401, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating token: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/api-key/generate")
async def generate_api_key(
    user_id: str, 
    permissions: List[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Generate API key for user"""
    try:
        # Check if user has permission to generate API keys
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_MANAGE):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = api_key_manager.generate_api_key(user_id, permissions)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/api-key/validate")
async def validate_api_key(api_key: str):
    """Validate API key"""
    try:
        result = api_key_manager.validate_api_key(api_key)
        
        if not result["valid"]:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/auth/api-key/{api_key}")
async def revoke_api_key(
    api_key: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Revoke API key"""
    try:
        # Check if user has permission to manage API keys
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_MANAGE):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = api_key_manager.revoke_api_key(api_key)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# User management endpoints
@app.post("/users/{user_id}/role")
async def assign_user_role(
    user_id: str,
    role: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Assign role to user"""
    try:
        # Check if user has permission to manage roles
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_MANAGE_ROLES):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        try:
            role_enum = Role(role.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
        
        result = permission_manager.assign_role(user_id, role_enum)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning user role: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{user_id}/role")
async def get_user_role(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get user's role"""
    try:
        # Check if user has permission to view users
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = permission_manager.get_user_role(user_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user role: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get user's permissions"""
    try:
        # Users can view their own permissions, admins can view any
        if user_id != current_user["user_id"] and not permission_manager.has_permission(current_user["user_id"], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = permission_manager.get_user_permissions(user_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user permissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/users/{user_id}/permissions/grant")
async def grant_user_permission(
    user_id: str,
    permission: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Grant custom permission to user"""
    try:
        # Check if user has permission to manage permissions
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_MANAGE_ROLES):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        try:
            permission_enum = Permission(permission)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid permission: {permission}")
        
        result = permission_manager.grant_custom_permission(user_id, permission_enum)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error granting user permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/users/{user_id}/permissions/{permission}")
async def revoke_user_permission(
    user_id: str,
    permission: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Revoke custom permission from user"""
    try:
        # Check if user has permission to manage permissions
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_MANAGE_ROLES):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        try:
            permission_enum = Permission(permission)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid permission: {permission}")
        
        result = permission_manager.revoke_custom_permission(user_id, permission_enum)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking user permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Role and permission management endpoints
@app.get("/roles")
async def list_all_roles(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all available roles and their permissions"""
    try:
        # Check if user has permission to view roles
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = permission_manager.list_all_roles()
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing roles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/roles/{role}")
async def get_role_permissions(
    role: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all permissions for a specific role"""
    try:
        # Check if user has permission to view roles
        if not permission_manager.has_permission(current_user["user_id"], Permission.USER_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        try:
            role_enum = Role(role.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
        
        result = permission_manager.get_role_permissions(role_enum)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting role permissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auth/stats")
async def get_permission_stats(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get statistics about permissions and users"""
    try:
        # Check if user has permission to view security stats
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = permission_manager.get_permission_stats()
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting permission stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Protected endpoint example
@app.get("/protected/admin")
@require_role([Role.ADMIN])
async def admin_only_endpoint(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Admin-only endpoint example"""
    return {
        "status": "success",
        "message": "Welcome admin!",
        "user": {
            "user_id": current_user.get("user_id"),
            "username": current_user.get("username"),
            "role": str(current_user.get("role")),
            "permissions": current_user.get("permissions", []),
            "auth_type": current_user.get("auth_type")
        }
    }

@app.get("/protected/operator")
@require_role([Role.ADMIN, Role.OPERATOR])
async def operator_endpoint(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Operator and admin endpoint example"""
    return {
        "status": "success",
        "message": "Welcome operator!",
        "user": {
            "user_id": current_user.get("user_id"),
            "username": current_user.get("username"),
            "role": str(current_user.get("role")),
            "permissions": current_user.get("permissions", []),
            "auth_type": current_user.get("auth_type")
        }
    }

# Monitoring and metrics endpoints
@app.get("/metrics")
async def get_prometheus_metrics():
    """Get metrics in Prometheus format"""
    try:
        metrics = metrics_registry.get_all_metrics()
        
        # Convert to Prometheus text format
        prometheus_output = []
        
        for name, metric_data in metrics.items():
            prometheus_output.append(f"# HELP {name} {metric_data['description']}")
            prometheus_output.append(f"# TYPE {name} {metric_data['type']}")
            
            if metric_data['type'] == 'counter':
                for labels, value in metric_data['values'].items():
                    if labels != '_default':
                        prometheus_output.append(f"{name}{{{labels}}} {value}")
                    else:
                        prometheus_output.append(f"{name} {value}")
            
            elif metric_data['type'] == 'gauge':
                for labels, value in metric_data['values'].items():
                    if labels != '_default':
                        prometheus_output.append(f"{name}{{{labels}}} {value}")
                    else:
                        prometheus_output.append(f"{name} {value}")
            
            elif metric_data['type'] == 'histogram':
                for key, count in metric_data['counts'].items():
                    prometheus_output.append(f"{name}_count{{{key}}} {count}")
                for key, sum_val in metric_data['sums'].items():
                    prometheus_output.append(f"{name}_sum{{{key}}} {sum_val}")
        
        return Response(
            content="\n".join(prometheus_output),
            media_type="text/plain"
        )
        
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/summary")
async def get_metrics_summary():
    """Get metrics summary for dashboard"""
    try:
        summary = performance_monitor.get_performance_summary()
        
        # Add additional system metrics
        system_metrics = {
            "total_agents": len(agent_registry.agents) if agent_registry else 0,
            "active_agents": len([a for a in agent_registry.agents.values() if getattr(a, 'is_active', True)]) if agent_registry else 0,
            "total_tasks": len(task_distributor.task_queue._queue) if task_distributor and hasattr(task_distributor, 'task_queue') else 0,
            "load_balancer_strategy": load_balancer.strategy.value if load_balancer else "unknown"
        }
        
        return {
            "status": "success",
            "performance": summary,
            "system": system_metrics,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting metrics summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/health")
async def get_health_metrics():
    """Get health metrics for monitoring"""
    try:
        # Get system health metrics
        import psutil
        
        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        
        # Update performance monitor with system metrics
        performance_monitor.update_system_metrics(memory.used, cpu)
        
        health_metrics = {
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percentage": memory.percent
            },
            "cpu": {
                "percentage": cpu,
                "count": psutil.cpu_count()
            },
            "uptime": performance_monitor.get_performance_summary()["uptime_seconds"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return {
            "status": "success",
            "health": health_metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting health metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Alerting endpoints
@app.get("/alerts")
async def get_alerts(
    status: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get alerts with optional status filter"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        if status == "active":
            alerts = alert_manager.get_active_alerts()
        else:
            alerts = alert_manager.get_alert_history()
        
        return {
            "status": "success",
            "alerts": alerts,
            "total": len(alerts)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Resolve an alert"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_MANAGE):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        result = alert_manager.resolve_alert(alert_id)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/alerts/stats")
async def get_alert_stats(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get alert statistics"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        stats = alert_manager.get_alert_stats()
        
        return {
            "status": "success",
            "stats": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/alerts/rules")
async def get_alert_rules(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get alert rules"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        rules = [rule.to_dict() for rule in alert_manager.rules.values()]
        
        return {
            "status": "success",
            "rules": rules,
            "total": len(rules)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# SLA monitoring endpoints
@app.get("/sla")
async def get_sla_status(
    sla_id: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get SLA status"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_VIEW):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        if sla_id:
            sla_status = alert_manager.sla_monitor.get_sla_compliance(sla_id)
        else:
            sla_status = alert_manager.sla_monitor.get_all_sla_status()
        
        return {
            "status": "success",
            "sla": sla_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting SLA status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sla/{sla_id}/record")
async def record_sla_metric(
    sla_id: str,
    value: float,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Record SLA metric"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SECURITY_MANAGE):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        alert_manager.sla_monitor.record_metric(sla_id, value)
        
        return {
            "status": "success",
            "message": f"SLA metric recorded for {sla_id}",
            "value": value,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording SLA metric: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# System status endpoint with monitoring
@app.get("/system/status")
async def get_system_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get comprehensive system status"""
    try:
        if not permission_manager.has_permission(current_user["user_id"], Permission.SYSTEM_HEALTH):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Get various status information
        performance = performance_monitor.get_performance_summary()
        alerts = alert_manager.get_active_alerts()
        sla_status = alert_manager.sla_monitor.get_all_sla_status()
        
        # Get system health
        import psutil
        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        
        status = {
            "overall": "healthy" if len(alerts) == 0 else "degraded",
            "performance": performance,
            "alerts": {
                "active_count": len(alerts),
                "critical_count": len([a for a in alerts if a.get("severity") == "critical"]),
                "warning_count": len([a for a in alerts if a.get("severity") == "warning"])
            },
            "sla": {
                "overall_compliance": sla_status.get("overall_compliance", 100.0),
                "total_slas": sla_status.get("total_slas", 0)
            },
            "system": {
                "memory_usage": memory.percent,
                "cpu_usage": cpu,
                "uptime": performance["uptime_seconds"]
            },
            "services": {
                "agent_coordinator": "running",
                "agent_registry": "running" if agent_registry else "stopped",
                "load_balancer": "running" if load_balancer else "stopped",
                "task_distributor": "running" if task_distributor else "stopped"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Add middleware to record metrics for all requests
@app.middleware("http")
async def metrics_middleware(request, call_next):
    """Middleware to record request metrics"""
    start_time = time.time()
    
    response = await call_next(request)
    
    # Record request metrics
    duration = time.time() - start_time
    performance_monitor.record_request(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
        duration=duration
    )
    
    return response

# Add security headers middleware
@app.middleware("http")
async def security_headers_middleware(request, call_next):
    """Middleware to add security headers"""
    response = await call_next(request)
    
    headers = security_headers.get_security_headers()
    for header, value in headers.items():
        response.headers[header] = value
    
    return response

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "status": "error",
            "message": "Resource not found",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# Main function
def main():
    """Main function to run the application"""
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9001,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()
