"""
Multi-Modal Fusion and Advanced RL API Endpoints
REST API for multi-modal agent fusion and advanced reinforcement learning
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from aitbc.logging import get_logger

from ..storage import SessionDep
from ..services.multi_modal_fusion import MultiModalFusionEngine
from ..services.advanced_reinforcement_learning import AdvancedReinforcementLearningEngine, MarketplaceStrategyOptimizer, CrossDomainCapabilityIntegrator
from ..domain.agent_performance import (
    FusionModel, ReinforcementLearningConfig, AgentCapability,
    CreativeCapability
)

logger = get_logger(__name__)

router = APIRouter(prefix="/multi-modal-rl", tags=["multi-modal-rl"])


# Pydantic models for API requests/responses
class FusionModelRequest(BaseModel):
    """Request model for fusion model creation"""
    model_name: str
    fusion_type: str = Field(default="cross_domain")
    base_models: List[str]
    input_modalities: List[str]
    fusion_strategy: str = Field(default="ensemble_fusion")


class FusionModelResponse(BaseModel):
    """Response model for fusion model"""
    fusion_id: str
    model_name: str
    fusion_type: str
    base_models: List[str]
    input_modalities: List[str]
    fusion_strategy: str
    status: str
    fusion_performance: Dict[str, float]
    synergy_score: float
    robustness_score: float
    created_at: str
    trained_at: Optional[str]


class FusionRequest(BaseModel):
    """Request model for fusion inference"""
    fusion_id: str
    input_data: Dict[str, Any]


class FusionResponse(BaseModel):
    """Response model for fusion result"""
    fusion_type: str
    combined_result: Dict[str, Any]
    confidence: float
    metadata: Dict[str, Any]


class RLAgentRequest(BaseModel):
    """Request model for RL agent creation"""
    agent_id: str
    environment_type: str
    algorithm: str = Field(default="ppo")
    training_config: Dict[str, Any] = Field(default_factory=dict)


class RLAgentResponse(BaseModel):
    """Response model for RL agent"""
    config_id: str
    agent_id: str
    environment_type: str
    algorithm: str
    status: str
    learning_rate: float
    discount_factor: float
    exploration_rate: float
    max_episodes: int
    created_at: str
    trained_at: Optional[str]


class RLTrainingResponse(BaseModel):
    """Response model for RL training"""
    config_id: str
    final_performance: float
    convergence_episode: int
    training_episodes: int
    success_rate: float
    training_time: float


class StrategyOptimizationRequest(BaseModel):
    """Request model for strategy optimization"""
    agent_id: str
    strategy_type: str
    algorithm: str = Field(default="ppo")
    training_episodes: int = Field(default=500)


class StrategyOptimizationResponse(BaseModel):
    """Response model for strategy optimization"""
    success: bool
    config_id: str
    strategy_type: str
    algorithm: str
    final_performance: float
    convergence_episode: int
    training_episodes: int
    success_rate: float


class CapabilityIntegrationRequest(BaseModel):
    """Request model for capability integration"""
    agent_id: str
    capabilities: List[str]
    integration_strategy: str = Field(default="adaptive")


class CapabilityIntegrationResponse(BaseModel):
    """Response model for capability integration"""
    agent_id: str
    integration_strategy: str
    domain_capabilities: Dict[str, List[Dict[str, Any]]]
    synergy_score: float
    enhanced_capabilities: List[str]
    fusion_model_id: str
    integration_result: Dict[str, Any]


# API Endpoints

@router.post("/fusion/models", response_model=FusionModelResponse)
async def create_fusion_model(
    fusion_request: FusionModelRequest,
    session: SessionDep
) -> FusionModelResponse:
    """Create multi-modal fusion model"""
    
    fusion_engine = MultiModalFusionEngine()
    
    try:
        fusion_model = await fusion_engine.create_fusion_model(
            session=session,
            model_name=fusion_request.model_name,
            fusion_type=fusion_request.fusion_type,
            base_models=fusion_request.base_models,
            input_modalities=fusion_request.input_modalities,
            fusion_strategy=fusion_request.fusion_strategy
        )
        
        return FusionModelResponse(
            fusion_id=fusion_model.fusion_id,
            model_name=fusion_model.model_name,
            fusion_type=fusion_model.fusion_type,
            base_models=fusion_model.base_models,
            input_modalities=fusion_model.input_modalities,
            fusion_strategy=fusion_model.fusion_strategy,
            status=fusion_model.status,
            fusion_performance=fusion_model.fusion_performance,
            synergy_score=fusion_model.synergy_score,
            robustness_score=fusion_model.robustness_score,
            created_at=fusion_model.created_at.isoformat(),
            trained_at=fusion_model.trained_at.isoformat() if fusion_model.trained_at else None
        )
        
    except Exception as e:
        logger.error(f"Error creating fusion model: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/fusion/{fusion_id}/infer", response_model=FusionResponse)
async def fuse_modalities(
    fusion_id: str,
    fusion_request: FusionRequest,
    session: SessionDep
) -> FusionResponse:
    """Fuse modalities using trained model"""
    
    fusion_engine = MultiModalFusionEngine()
    
    try:
        fusion_result = await fusion_engine.fuse_modalities(
            session=session,
            fusion_id=fusion_id,
            input_data=fusion_request.input_data
        )
        
        return FusionResponse(
            fusion_type=fusion_result['fusion_type'],
            combined_result=fusion_result['combined_result'],
            confidence=fusion_result.get('confidence', 0.0),
            metadata={
                'modality_contributions': fusion_result.get('modality_contributions', {}),
                'attention_weights': fusion_result.get('attention_weights', {}),
                'optimization_gain': fusion_result.get('optimization_gain', 0.0)
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error during fusion: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/fusion/models")
async def list_fusion_models(
    session: SessionDep,
    status: Optional[str] = Query(default=None, description="Filter by status"),
    fusion_type: Optional[str] = Query(default=None, description="Filter by fusion type"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results")
) -> List[Dict[str, Any]]:
    """List fusion models"""
    
    try:
        query = select(FusionModel)
        
        if status:
            query = query.where(FusionModel.status == status)
        if fusion_type:
            query = query.where(FusionModel.fusion_type == fusion_type)
        
        models = session.execute(
            query.order_by(FusionModel.created_at.desc()).limit(limit)
        ).all()
        
        return [
            {
                "fusion_id": model.fusion_id,
                "model_name": model.model_name,
                "fusion_type": model.fusion_type,
                "base_models": model.base_models,
                "input_modalities": model.input_modalities,
                "fusion_strategy": model.fusion_strategy,
                "status": model.status,
                "fusion_performance": model.fusion_performance,
                "synergy_score": model.synergy_score,
                "robustness_score": model.robustness_score,
                "computational_complexity": model.computational_complexity,
                "memory_requirement": model.memory_requirement,
                "inference_time": model.inference_time,
                "deployment_count": model.deployment_count,
                "performance_stability": model.performance_stability,
                "created_at": model.created_at.isoformat(),
                "trained_at": model.trained_at.isoformat() if model.trained_at else None
            }
            for model in models
        ]
        
    except Exception as e:
        logger.error(f"Error listing fusion models: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rl/agents", response_model=RLAgentResponse)
async def create_rl_agent(
    agent_request: RLAgentRequest,
    session: SessionDep
) -> RLAgentResponse:
    """Create RL agent for marketplace strategies"""
    
    rl_engine = AdvancedReinforcementLearningEngine()
    
    try:
        rl_config = await rl_engine.create_rl_agent(
            session=session,
            agent_id=agent_request.agent_id,
            environment_type=agent_request.environment_type,
            algorithm=agent_request.algorithm,
            training_config=agent_request.training_config
        )
        
        return RLAgentResponse(
            config_id=rl_config.config_id,
            agent_id=rl_config.agent_id,
            environment_type=rl_config.environment_type,
            algorithm=rl_config.algorithm,
            status=rl_config.status,
            learning_rate=rl_config.learning_rate,
            discount_factor=rl_config.discount_factor,
            exploration_rate=rl_config.exploration_rate,
            max_episodes=rl_config.max_episodes,
            created_at=rl_config.created_at.isoformat(),
            trained_at=rl_config.trained_at.isoformat() if rl_config.trained_at else None
        )
        
    except Exception as e:
        logger.error(f"Error creating RL agent: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.websocket("/fusion/{fusion_id}/stream")
async def fuse_modalities_stream(
    websocket: WebSocket,
    fusion_id: str,
    session: SessionDep
):
    """Stream modalities and receive fusion results via WebSocket for high performance"""
    await websocket.accept()
    fusion_engine = MultiModalFusionEngine()
    
    try:
        while True:
            # Receive text data (JSON) containing input modalities
            data = await websocket.receive_json()
            
            # Start timing
            start_time = datetime.utcnow()
            
            # Process fusion
            fusion_result = await fusion_engine.fuse_modalities(
                session=session,
                fusion_id=fusion_id,
                input_data=data
            )
            
            # End timing
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Send result back
            await websocket.send_json({
                "fusion_type": fusion_result['fusion_type'],
                "combined_result": fusion_result['combined_result'],
                "confidence": fusion_result.get('confidence', 0.0),
                "metadata": {
                    "processing_time": processing_time,
                    "fusion_strategy": fusion_result.get('strategy', 'unknown'),
                    "protocol": "websocket"
                }
            })
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from fusion stream {fusion_id}")
    except Exception as e:
        logger.error(f"Error in fusion stream: {str(e)}")
        try:
            await websocket.send_json({"error": str(e)})
            await websocket.close(code=1011, reason=str(e))
        except:
            pass


@router.get("/rl/agents/{agent_id}")
async def get_rl_agents(
    agent_id: str,
    session: SessionDep,
    status: Optional[str] = Query(default=None, description="Filter by status"),
    algorithm: Optional[str] = Query(default=None, description="Filter by algorithm"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of results")
) -> List[Dict[str, Any]]:
    """Get RL agents for agent"""
    
    try:
        query = select(ReinforcementLearningConfig).where(ReinforcementLearningConfig.agent_id == agent_id)
        
        if status:
            query = query.where(ReinforcementLearningConfig.status == status)
        if algorithm:
            query = query.where(ReinforcementLearningConfig.algorithm == algorithm)
        
        configs = session.execute(
            query.order_by(ReinforcementLearningConfig.created_at.desc()).limit(limit)
        ).all()
        
        return [
            {
                "config_id": config.config_id,
                "agent_id": config.agent_id,
                "environment_type": config.environment_type,
                "algorithm": config.algorithm,
                "status": config.status,
                "learning_rate": config.learning_rate,
                "discount_factor": config.discount_factor,
                "exploration_rate": config.exploration_rate,
                "batch_size": config.batch_size,
                "network_layers": config.network_layers,
                "activation_functions": config.activation_functions,
                "max_episodes": config.max_episodes,
                "max_steps_per_episode": config.max_steps_per_episode,
                "action_space": config.action_space,
                "state_space": config.state_space,
                "reward_history": config.reward_history,
                "success_rate_history": config.success_rate_history,
                "convergence_episode": config.convergence_episode,
                "training_progress": config.training_progress,
                "deployment_performance": config.deployment_performance,
                "deployment_count": config.deployment_count,
                "created_at": config.created_at.isoformat(),
                "trained_at": config.trained_at.isoformat() if config.trained_at else None,
                "deployed_at": config.deployed_at.isoformat() if config.deployed_at else None
            }
            for config in configs
        ]
        
    except Exception as e:
        logger.error(f"Error getting RL agents for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rl/optimize-strategy", response_model=StrategyOptimizationResponse)
async def optimize_strategy(
    optimization_request: StrategyOptimizationRequest,
    session: SessionDep
) -> StrategyOptimizationResponse:
    """Optimize agent strategy using RL"""
    
    strategy_optimizer = MarketplaceStrategyOptimizer()
    
    try:
        result = await strategy_optimizer.optimize_agent_strategy(
            session=session,
            agent_id=optimization_request.agent_id,
            strategy_type=optimization_request.strategy_type,
            algorithm=optimization_request.algorithm,
            training_episodes=optimization_request.training_episodes
        )
        
        return StrategyOptimizationResponse(
            success=result['success'],
            config_id=result.get('config_id'),
            strategy_type=result.get('strategy_type'),
            algorithm=result.get('algorithm'),
            final_performance=result.get('final_performance', 0.0),
            convergence_episode=result.get('convergence_episode', 0),
            training_episodes=result.get('training_episodes', 0),
            success_rate=result.get('success_rate', 0.0)
        )
        
    except Exception as e:
        logger.error(f"Error optimizing strategy: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rl/deploy-strategy")
async def deploy_strategy(
    config_id: str,
    deployment_context: Dict[str, Any],
    session: SessionDep
) -> Dict[str, Any]:
    """Deploy trained strategy"""
    
    strategy_optimizer = MarketplaceStrategyOptimizer()
    
    try:
        result = await strategy_optimizer.deploy_strategy(
            session=session,
            config_id=config_id,
            deployment_context=deployment_context
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deploying strategy: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/capabilities/integrate", response_model=CapabilityIntegrationResponse)
async def integrate_capabilities(
    integration_request: CapabilityIntegrationRequest,
    session: SessionDep
) -> CapabilityIntegrationResponse:
    """Integrate capabilities across domains"""
    
    capability_integrator = CrossDomainCapabilityIntegrator()
    
    try:
        result = await capability_integrator.integrate_cross_domain_capabilities(
            session=session,
            agent_id=integration_request.agent_id,
            capabilities=integration_request.capabilities,
            integration_strategy=integration_request.integration_strategy
        )
        
        # Format domain capabilities for response
        formatted_domain_caps = {}
        for domain, caps in result['domain_capabilities'].items():
            formatted_domain_caps[domain] = [
                {
                    "capability_id": cap.capability_id,
                    "capability_name": cap.capability_name,
                    "capability_type": cap.capability_type,
                    "skill_level": cap.skill_level,
                    "proficiency_score": cap.proficiency_score
                }
                for cap in caps
            ]
        
        return CapabilityIntegrationResponse(
            agent_id=result['agent_id'],
            integration_strategy=result['integration_strategy'],
            domain_capabilities=formatted_domain_caps,
            synergy_score=result['synergy_score'],
            enhanced_capabilities=result['enhanced_capabilities'],
            fusion_model_id=result['fusion_model_id'],
            integration_result=result['integration_result']
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error integrating capabilities: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/capabilities/{agent_id}/domains")
async def get_agent_domain_capabilities(
    agent_id: str,
    session: SessionDep,
    domain: Optional[str] = Query(default=None, description="Filter by domain"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results")
) -> List[Dict[str, Any]]:
    """Get agent capabilities grouped by domain"""
    
    try:
        query = select(AgentCapability).where(AgentCapability.agent_id == agent_id)
        
        if domain:
            query = query.where(AgentCapability.domain_area == domain)
        
        capabilities = session.execute(
            query.order_by(AgentCapability.skill_level.desc()).limit(limit)
        ).all()
        
        # Group by domain
        domain_capabilities = {}
        for cap in capabilities:
            if cap.domain_area not in domain_capabilities:
                domain_capabilities[cap.domain_area] = []
            
            domain_capabilities[cap.domain_area].append({
                "capability_id": cap.capability_id,
                "capability_name": cap.capability_name,
                "capability_type": cap.capability_type,
                "skill_level": cap.skill_level,
                "proficiency_score": cap.proficiency_score,
                "specialization_areas": cap.specialization_areas,
                "learning_rate": cap.learning_rate,
                "adaptation_speed": cap.adaptation_speed,
                "certified": cap.certified,
                "certification_level": cap.certification_level,
                "status": cap.status,
                "acquired_at": cap.acquired_at.isoformat(),
                "last_improved": cap.last_improved.isoformat() if cap.last_improved else None
            })
        
        return [
            {
                "domain": domain,
                "capabilities": caps,
                "total_capabilities": len(caps),
                "average_skill_level": sum(cap["skill_level"] for cap in caps) / len(caps) if caps else 0.0,
                "highest_skill_level": max(cap["skill_level"] for cap in caps) if caps else 0.0
            }
            for domain, caps in domain_capabilities.items()
        ]
        
    except Exception as e:
        logger.error(f"Error getting domain capabilities for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/creative-capabilities/{agent_id}")
async def get_creative_capabilities(
    agent_id: str,
    session: SessionDep,
    creative_domain: Optional[str] = Query(default=None, description="Filter by creative domain"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results")
) -> List[Dict[str, Any]]:
    """Get creative capabilities for agent"""
    
    try:
        query = select(CreativeCapability).where(CreativeCapability.agent_id == agent_id)
        
        if creative_domain:
            query = query.where(CreativeCapability.creative_domain == creative_domain)
        
        capabilities = session.execute(
            query.order_by(CreativeCapability.originality_score.desc()).limit(limit)
        ).all()
        
        return [
            {
                "capability_id": cap.capability_id,
                "agent_id": cap.agent_id,
                "creative_domain": cap.creative_domain,
                "capability_type": cap.capability_type,
                "originality_score": cap.originality_score,
                "novelty_score": cap.novelty_score,
                "aesthetic_quality": cap.aesthetic_quality,
                "coherence_score": cap.coherence_score,
                "generation_models": cap.generation_models,
                "style_variety": cap.style_variety,
                "output_quality": cap.output_quality,
                "creative_learning_rate": cap.creative_learning_rate,
                "style_adaptation": cap.style_adaptation,
                "cross_domain_transfer": cap.cross_domain_transfer,
                "creative_specializations": cap.creative_specializations,
                "tool_proficiency": cap.tool_proficiency,
                "domain_knowledge": cap.domain_knowledge,
                "creations_generated": cap.creations_generated,
                "user_ratings": cap.user_ratings,
                "expert_evaluations": cap.expert_evaluations,
                "status": cap.status,
                "certification_level": cap.certification_level,
                "created_at": cap.created_at.isoformat(),
                "last_evaluation": cap.last_evaluation.isoformat() if cap.last_evaluation else None
            }
            for cap in capabilities
        ]
        
    except Exception as e:
        logger.error(f"Error getting creative capabilities for agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/fusion-performance")
async def get_fusion_performance_analytics(
    session: SessionDep,
    agent_ids: Optional[List[str]] = Query(default=[], description="List of agent IDs"),
    fusion_type: Optional[str] = Query(default=None, description="Filter by fusion type"),
    period: str = Query(default="7d", description="Time period")
) -> Dict[str, Any]:
    """Get fusion performance analytics"""
    
    try:
        query = select(FusionModel)
        
        if fusion_type:
            query = query.where(FusionModel.fusion_type == fusion_type)
        
        models = session.execute(query).all()
        
        # Filter by agent IDs if provided (by checking base models)
        if agent_ids:
            filtered_models = []
            for model in models:
                # Check if any base model belongs to specified agents
                if any(agent_id in str(base_model) for base_model in model.base_models for agent_id in agent_ids):
                    filtered_models.append(model)
            models = filtered_models
        
        # Calculate analytics
        total_models = len(models)
        ready_models = len([m for m in models if m.status == "ready"])
        
        if models:
            avg_synergy = sum(m.synergy_score for m in models) / len(models)
            avg_robustness = sum(m.robustness_score for m in models) / len(models)
            
            # Performance metrics
            performance_metrics = {}
            for model in models:
                if model.fusion_performance:
                    for metric, value in model.fusion_performance.items():
                        if metric not in performance_metrics:
                            performance_metrics[metric] = []
                        performance_metrics[metric].append(value)
            
            avg_performance = {}
            for metric, values in performance_metrics.items():
                avg_performance[metric] = sum(values) / len(values)
            
            # Fusion strategy distribution
            strategy_distribution = {}
            for model in models:
                strategy = model.fusion_strategy
                strategy_distribution[strategy] = strategy_distribution.get(strategy, 0) + 1
        else:
            avg_synergy = 0.0
            avg_robustness = 0.0
            avg_performance = {}
            strategy_distribution = {}
        
        return {
            "period": period,
            "total_models": total_models,
            "ready_models": ready_models,
            "readiness_rate": ready_models / total_models if total_models > 0 else 0.0,
            "average_synergy_score": avg_synergy,
            "average_robustness_score": avg_robustness,
            "average_performance": avg_performance,
            "strategy_distribution": strategy_distribution,
            "top_performing_models": sorted(
                [
                    {
                        "fusion_id": model.fusion_id,
                        "model_name": model.model_name,
                        "synergy_score": model.synergy_score,
                        "robustness_score": model.robustness_score,
                        "deployment_count": model.deployment_count
                    }
                    for model in models
                ],
                key=lambda x: x["synergy_score"],
                reverse=True
            )[:10]
        }
        
    except Exception as e:
        logger.error(f"Error getting fusion performance analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/rl-performance")
async def get_rl_performance_analytics(
    session: SessionDep,
    agent_ids: Optional[List[str]] = Query(default=[], description="List of agent IDs"),
    algorithm: Optional[str] = Query(default=None, description="Filter by algorithm"),
    environment_type: Optional[str] = Query(default=None, description="Filter by environment type"),
    period: str = Query(default="7d", description="Time period")
) -> Dict[str, Any]:
    """Get RL performance analytics"""
    
    try:
        query = select(ReinforcementLearningConfig)
        
        if agent_ids:
            query = query.where(ReinforcementLearningConfig.agent_id.in_(agent_ids))
        if algorithm:
            query = query.where(ReinforcementLearningConfig.algorithm == algorithm)
        if environment_type:
            query = query.where(ReinforcementLearningConfig.environment_type == environment_type)
        
        configs = session.execute(query).all()
        
        # Calculate analytics
        total_configs = len(configs)
        ready_configs = len([c for c in configs if c.status == "ready"])
        
        if configs:
            # Algorithm distribution
            algorithm_distribution = {}
            for config in configs:
                alg = config.algorithm
                algorithm_distribution[alg] = algorithm_distribution.get(alg, 0) + 1
            
            # Environment distribution
            environment_distribution = {}
            for config in configs:
                env = config.environment_type
                environment_distribution[env] = environment_distribution.get(env, 0) + 1
            
            # Performance metrics
            final_performances = []
            success_rates = []
            convergence_episodes = []
            
            for config in configs:
                if config.reward_history:
                    final_performances.append(np.mean(config.reward_history[-10:]))
                if config.success_rate_history:
                    success_rates.append(np.mean(config.success_rate_history[-10:]))
                if config.convergence_episode:
                    convergence_episodes.append(config.convergence_episode)
            
            avg_performance = np.mean(final_performances) if final_performances else 0.0
            avg_success_rate = np.mean(success_rates) if success_rates else 0.0
            avg_convergence = np.mean(convergence_episodes) if convergence_episodes else 0.0
        else:
            algorithm_distribution = {}
            environment_distribution = {}
            avg_performance = 0.0
            avg_success_rate = 0.0
            avg_convergence = 0.0
        
        return {
            "period": period,
            "total_agents": len(set(c.agent_id for c in configs)),
            "total_configs": total_configs,
            "ready_configs": ready_configs,
            "readiness_rate": ready_configs / total_configs if total_configs > 0 else 0.0,
            "average_performance": avg_performance,
            "average_success_rate": avg_success_rate,
            "average_convergence_episode": avg_convergence,
            "algorithm_distribution": algorithm_distribution,
            "environment_distribution": environment_distribution,
            "top_performing_agents": sorted(
                [
                    {
                        "agent_id": config.agent_id,
                        "algorithm": config.algorithm,
                        "environment_type": config.environment_type,
                        "final_performance": np.mean(config.reward_history[-10:]) if config.reward_history else 0.0,
                        "convergence_episode": config.convergence_episode,
                        "deployment_count": config.deployment_count
                    }
                    for config in configs
                ],
                key=lambda x: x["final_performance"],
                reverse=True
            )[:10]
        }
        
    except Exception as e:
        logger.error(f"Error getting RL performance analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check for multi-modal and RL services"""
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "services": {
            "multi_modal_fusion_engine": "operational",
            "advanced_rl_engine": "operational",
            "marketplace_strategy_optimizer": "operational",
            "cross_domain_capability_integrator": "operational"
        }
    }
