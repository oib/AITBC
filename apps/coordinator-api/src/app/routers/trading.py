"""
P2P Trading Protocol API Endpoints
REST API for agent-to-agent trading, matching, negotiation, and settlement
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from aitbc.logging import get_logger

from ..storage import SessionDep
from ..services.trading_service import P2PTradingProtocol
from ..domain.trading import (
    TradeRequest, TradeMatch, TradeNegotiation, TradeAgreement, TradeSettlement,
    TradeStatus, TradeType, NegotiationStatus, SettlementType
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/trading", tags=["trading"])


# Pydantic models for API requests/responses
class TradeRequestRequest(BaseModel):
    """Request model for creating trade request"""
    buyer_agent_id: str
    trade_type: TradeType
    title: str = Field(..., max_length=200)
    description: str = Field(default="", max_length=1000)
    requirements: Dict[str, Any] = Field(..., description="Trade requirements and specifications")
    budget_range: Dict[str, float] = Field(..., description="Budget range with min and max")
    start_time: Optional[str] = Field(default=None, description="Start time (ISO format)")
    end_time: Optional[str] = Field(default=None, description="End time (ISO format)")
    duration_hours: Optional[int] = Field(default=None, description="Duration in hours")
    urgency_level: str = Field(default="normal", description="urgency level")
    preferred_regions: List[str] = Field(default_factory=list, description="Preferred regions")
    excluded_regions: List[str] = Field(default_factory=list, description="Excluded regions")
    service_level_required: str = Field(default="standard", description="Service level required")
    tags: List[str] = Field(default_factory=list, description="Trade tags")
    expires_at: Optional[str] = Field(default=None, description="Expiration time (ISO format)")


class TradeRequestResponse(BaseModel):
    """Response model for trade request"""
    request_id: str
    buyer_agent_id: str
    trade_type: str
    title: str
    description: str
    requirements: Dict[str, Any]
    budget_range: Dict[str, float]
    status: str
    match_count: int
    best_match_score: float
    created_at: str
    updated_at: str
    expires_at: Optional[str]


class TradeMatchResponse(BaseModel):
    """Response model for trade match"""
    match_id: str
    request_id: str
    buyer_agent_id: str
    seller_agent_id: str
    match_score: float
    confidence_level: float
    price_compatibility: float
    specification_compatibility: float
    timing_compatibility: float
    reputation_compatibility: float
    geographic_compatibility: float
    seller_offer: Dict[str, Any]
    proposed_terms: Dict[str, Any]
    status: str
    created_at: str
    expires_at: Optional[str]


class NegotiationRequest(BaseModel):
    """Request model for initiating negotiation"""
    match_id: str
    initiator: str = Field(..., description="negotiation initiator: buyer or seller")
    strategy: str = Field(default="balanced", description="negotiation strategy")


class NegotiationResponse(BaseModel):
    """Response model for negotiation"""
    negotiation_id: str
    match_id: str
    buyer_agent_id: str
    seller_agent_id: str
    status: str
    negotiation_round: int
    current_terms: Dict[str, Any]
    negotiation_strategy: str
    auto_accept_threshold: float
    created_at: str
    started_at: Optional[str]
    expires_at: Optional[str]


class AgreementResponse(BaseModel):
    """Response model for trade agreement"""
    agreement_id: str
    negotiation_id: str
    buyer_agent_id: str
    seller_agent_id: str
    trade_type: str
    title: str
    agreed_terms: Dict[str, Any]
    total_price: float
    settlement_type: str
    status: str
    created_at: str
    signed_at: str
    starts_at: Optional[str]
    ends_at: Optional[str]


class SettlementResponse(BaseModel):
    """Response model for settlement"""
    settlement_id: str
    agreement_id: str
    settlement_type: str
    total_amount: float
    currency: str
    payment_status: str
    transaction_id: Optional[str]
    platform_fee: float
    net_amount_seller: float
    status: str
    initiated_at: str
    processed_at: Optional[str]
    completed_at: Optional[str]


class TradingSummaryResponse(BaseModel):
    """Response model for trading summary"""
    agent_id: str
    trade_requests: int
    trade_matches: int
    negotiations: int
    agreements: int
    success_rate: float
    average_match_score: float
    total_trade_volume: float
    recent_activity: Dict[str, Any]


# API Endpoints

@router.post("/requests", response_model=TradeRequestResponse)
async def create_trade_request(
    request_data: TradeRequestRequest,
    session: SessionDep
) -> TradeRequestResponse:
    """Create a new trade request"""
    
    trading_protocol = P2PTradingProtocol(session)
    
    try:
        # Parse optional datetime fields
        start_time = None
        end_time = None
        expires_at = None
        
        if request_data.start_time:
            start_time = datetime.fromisoformat(request_data.start_time)
        if request_data.end_time:
            end_time = datetime.fromisoformat(request_data.end_time)
        if request_data.expires_at:
            expires_at = datetime.fromisoformat(request_data.expires_at)
        
        # Create trade request
        trade_request = await trading_protocol.create_trade_request(
            buyer_agent_id=request_data.buyer_agent_id,
            trade_type=request_data.trade_type,
            title=request_data.title,
            description=request_data.description,
            requirements=request_data.requirements,
            budget_range=request_data.budget_range,
            start_time=start_time,
            end_time=end_time,
            duration_hours=request_data.duration_hours,
            urgency_level=request_data.urgency_level,
            preferred_regions=request_data.preferred_regions,
            excluded_regions=request_data.excluded_regions,
            service_level_required=request_data.service_level_required,
            tags=request_data.tags,
            expires_at=expires_at
        )
        
        return TradeRequestResponse(
            request_id=trade_request.request_id,
            buyer_agent_id=trade_request.buyer_agent_id,
            trade_type=trade_request.trade_type.value,
            title=trade_request.title,
            description=trade_request.description,
            requirements=trade_request.requirements,
            budget_range=trade_request.budget_range,
            status=trade_request.status.value,
            match_count=trade_request.match_count,
            best_match_score=trade_request.best_match_score,
            created_at=trade_request.created_at.isoformat(),
            updated_at=trade_request.updated_at.isoformat(),
            expires_at=trade_request.expires_at.isoformat() if trade_request.expires_at else None
        )
        
    except Exception as e:
        logger.error(f"Error creating trade request: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/requests/{request_id}", response_model=TradeRequestResponse)
async def get_trade_request(
    request_id: str,
    session: SessionDep
) -> TradeRequestResponse:
    """Get trade request details"""
    
    try:
        trade_request = session.execute(
            select(TradeRequest).where(TradeRequest.request_id == request_id)
        ).first()
        
        if not trade_request:
            raise HTTPException(status_code=404, detail="Trade request not found")
        
        return TradeRequestResponse(
            request_id=trade_request.request_id,
            buyer_agent_id=trade_request.buyer_agent_id,
            trade_type=trade_request.trade_type.value,
            title=trade_request.title,
            description=trade_request.description,
            requirements=trade_request.requirements,
            budget_range=trade_request.budget_range,
            status=trade_request.status.value,
            match_count=trade_request.match_count,
            best_match_score=trade_request.best_match_score,
            created_at=trade_request.created_at.isoformat(),
            updated_at=trade_request.updated_at.isoformat(),
            expires_at=trade_request.expires_at.isoformat() if trade_request.expires_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trade request {request_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/requests/{request_id}/matches")
async def find_matches(
    request_id: str,
    session: SessionDep
) -> List[str]:
    """Find matching sellers for a trade request"""
    
    trading_protocol = P2PTradingProtocol(session)
    
    try:
        matches = await trading_protocol.find_matches(request_id)
        return matches
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error finding matches for request {request_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/requests/{request_id}/matches")
async def get_trade_matches(
    request_id: str,
    session: SessionDep
) -> List[TradeMatchResponse]:
    """Get trade matches for a request"""
    
    try:
        matches = session.execute(
            select(TradeMatch).where(TradeMatch.request_id == request_id)
            .order_by(TradeMatch.match_score.desc())
        ).all()
        
        return [
            TradeMatchResponse(
                match_id=match.match_id,
                request_id=match.request_id,
                buyer_agent_id=match.buyer_agent_id,
                seller_agent_id=match.seller_agent_id,
                match_score=match.match_score,
                confidence_level=match.confidence_level,
                price_compatibility=match.price_compatibility,
                specification_compatibility=match.specification_compatibility,
                timing_compatibility=match.timing_compatibility,
                reputation_compatibility=match.reputation_compatibility,
                geographic_compatibility=match.geographic_compatibility,
                seller_offer=match.seller_offer,
                proposed_terms=match.proposed_terms,
                status=match.status.value,
                created_at=match.created_at.isoformat(),
                expires_at=match.expires_at.isoformat() if match.expires_at else None
            )
            for match in matches
        ]
        
    except Exception as e:
        logger.error(f"Error getting trade matches for request {request_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/negotiations", response_model=NegotiationResponse)
async def initiate_negotiation(
    negotiation_data: NegotiationRequest,
    session: SessionDep
) -> NegotiationResponse:
    """Initiate negotiation between buyer and seller"""
    
    trading_protocol = P2PTradingProtocol(session)
    
    try:
        negotiation = await trading_protocol.initiate_negotiation(
            match_id=negotiation_data.match_id,
            initiator=negotiation_data.initiator,
            strategy=negotiation_data.strategy
        )
        
        return NegotiationResponse(
            negotiation_id=negotiation.negotiation_id,
            match_id=negotiation.match_id,
            buyer_agent_id=negotiation.buyer_agent_id,
            seller_agent_id=negotiation.seller_agent_id,
            status=negotiation.status.value,
            negotiation_round=negotiation.negotiation_round,
            current_terms=negotiation.current_terms,
            negotiation_strategy=negotiation.negotiation_strategy,
            auto_accept_threshold=negotiation.auto_accept_threshold,
            created_at=negotiation.created_at.isoformat(),
            started_at=negotiation.started_at.isoformat() if negotiation.started_at else None,
            expires_at=negotiation.expires_at.isoformat() if negotiation.expires_at else None
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error initiating negotiation: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/negotiations/{negotiation_id}", response_model=NegotiationResponse)
async def get_negotiation(
    negotiation_id: str,
    session: SessionDep
) -> NegotiationResponse:
    """Get negotiation details"""
    
    try:
        negotiation = session.execute(
            select(TradeNegotiation).where(TradeNegotiation.negotiation_id == negotiation_id)
        ).first()
        
        if not negotiation:
            raise HTTPException(status_code=404, detail="Negotiation not found")
        
        return NegotiationResponse(
            negotiation_id=negotiation.negotiation_id,
            match_id=negotiation.match_id,
            buyer_agent_id=negotiation.buyer_agent_id,
            seller_agent_id=negotiation.seller_agent_id,
            status=negotiation.status.value,
            negotiation_round=negotiation.negotiation_round,
            current_terms=negotiation.current_terms,
            negotiation_strategy=negotiation.negotiation_strategy,
            auto_accept_threshold=negotiation.auto_accept_threshold,
            created_at=negotiation.created_at.isoformat(),
            started_at=negotiation.started_at.isoformat() if negotiation.started_at else None,
            expires_at=negotiation.expires_at.isoformat() if negotiation.expires_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting negotiation {negotiation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/matches/{match_id}")
async def get_trade_match(
    match_id: str,
    session: SessionDep
) -> TradeMatchResponse:
    """Get trade match details"""
    
    try:
        match = session.execute(
            select(TradeMatch).where(TradeMatch.match_id == match_id)
        ).first()
        
        if not match:
            raise HTTPException(status_code=404, detail="Trade match not found")
        
        return TradeMatchResponse(
            match_id=match.match_id,
            request_id=match.request_id,
            buyer_agent_id=match.buyer_agent_id,
            seller_agent_id=match.seller_agent_id,
            match_score=match.match_score,
            confidence_level=match.confidence_level,
            price_compatibility=match.price_compatibility,
            specification_compatibility=match.specification_compatibility,
            timing_compatibility=match.timing_compatibility,
            reputation_compatibility=match.reputation_compatibility,
            geographic_compatibility=match.geographic_compatibility,
            seller_offer=match.seller_offer,
            proposed_terms=match.proposed_terms,
            status=match.status.value,
            created_at=match.created_at.isoformat(),
            expires_at=match.expires_at.isoformat() if match.expires_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trade match {match_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/agents/{agent_id}/summary", response_model=TradingSummaryResponse)
async def get_trading_summary(
    agent_id: str,
    session: SessionDep
) -> TradingSummaryResponse:
    """Get comprehensive trading summary for an agent"""
    
    trading_protocol = P2PTradingProtocol(session)
    
    try:
        summary = await trading_protocol.get_trading_summary(agent_id)
        
        return TradingSummaryResponse(**summary)
        
    except Exception as e:
        logger.error(f"Error getting trading summary for {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/requests")
async def list_trade_requests(
    agent_id: Optional[str] = Query(default=None, description="Filter by agent ID"),
    trade_type: Optional[str] = Query(default=None, description="Filter by trade type"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: SessionDep
) -> List[TradeRequestResponse]:
    """List trade requests with filters"""
    
    try:
        query = select(TradeRequest)
        
        if agent_id:
            query = query.where(TradeRequest.buyer_agent_id == agent_id)
        if trade_type:
            query = query.where(TradeRequest.trade_type == trade_type)
        if status:
            query = query.where(TradeRequest.status == status)
        
        requests = session.execute(
            query.order_by(TradeRequest.created_at.desc()).limit(limit)
        ).all()
        
        return [
            TradeRequestResponse(
                request_id=request.request_id,
                buyer_agent_id=request.buyer_agent_id,
                trade_type=request.trade_type.value,
                title=request.title,
                description=request.description,
                requirements=request.requirements,
                budget_range=request.budget_range,
                status=request.status.value,
                match_count=request.match_count,
                best_match_score=request.best_match_score,
                created_at=request.created_at.isoformat(),
                updated_at=request.updated_at.isoformat(),
                expires_at=request.expires_at.isoformat() if request.expires_at else None
            )
            for request in requests
        ]
        
    except Exception as e:
        logger.error(f"Error listing trade requests: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/matches")
async def list_trade_matches(
    agent_id: Optional[str] = Query(default=None, description="Filter by agent ID"),
    min_score: Optional[float] = Query(default=None, description="Minimum match score"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: SessionDep
) -> List[TradeMatchResponse]:
    """List trade matches with filters"""
    
    try:
        query = select(TradeMatch)
        
        if agent_id:
            query = query.where(
                or_(
                    TradeMatch.buyer_agent_id == agent_id,
                    TradeMatch.seller_agent_id == agent_id
                )
            )
        if min_score:
            query = query.where(TradeMatch.match_score >= min_score)
        if status:
            query = query.where(TradeMatch.status == status)
        
        matches = session.execute(
            query.order_by(TradeMatch.match_score.desc()).limit(limit)
        ).all()
        
        return [
            TradeMatchResponse(
                match_id=match.match_id,
                request_id=match.request_id,
                buyer_agent_id=match.buyer_agent_id,
                seller_agent_id=match.seller_agent_id,
                match_score=match.match_score,
                confidence_level=match.confidence_level,
                price_compatibility=match.price_compatibility,
                specification_compatibility=match.specification_compatibility,
                timing_compatibility=match.timing_compatibility,
                reputation_compatibility=match.reputation_compatibility,
                geographic_compatibility=match.geographic_compatibility,
                seller_offer=match.seller_offer,
                proposed_terms=match.proposed_terms,
                status=match.status.value,
                created_at=match.created_at.isoformat(),
                expires_at=match.expires_at.isoformat() if match.expires_at else None
            )
            for match in matches
        ]
        
    except Exception as e:
        logger.error(f"Error listing trade matches: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/negotiations")
async def list_negotiations(
    agent_id: Optional[str] = Query(default=None, description="Filter by agent ID"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    strategy: Optional[str] = Query(default=None, description="Filter by strategy"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of results"),
    session: SessionDep
) -> List[NegotiationResponse]:
    """List negotiations with filters"""
    
    try:
        query = select(TradeNegotiation)
        
        if agent_id:
            query = query.where(
                or_(
                    TradeNegotiation.buyer_agent_id == agent_id,
                    TradeNegotiation.seller_agent_id == agent_id
                )
            )
        if status:
            query = query.where(TradeNegotiation.status == status)
        if strategy:
            query = query.where(TradeNegotiation.negotiation_strategy == strategy)
        
        negotiations = session.execute(
            query.order_by(TradeNegotiation.created_at.desc()).limit(limit)
        ).all()
        
        return [
            NegotiationResponse(
                negotiation_id=negotiation.negotiation_id,
                match_id=negotiation.match_id,
                buyer_agent_id=negotiation.buyer_agent_id,
                seller_agent_id=negotiation.seller_agent_id,
                status=negotiation.status.value,
                negotiation_round=negotiation.negotiation_round,
                current_terms=negotiation.current_terms,
                negotiation_strategy=negotiation.negotiation_strategy,
                auto_accept_threshold=negotiation.auto_accept_threshold,
                created_at=negotiation.created_at.isoformat(),
                started_at=negotiation.started_at.isoformat() if negotiation.started_at else None,
                expires_at=negotiation.expires_at.isoformat() if negotiation.expires_at else None
            )
            for negotiation in negotiations
        ]
        
    except Exception as e:
        logger.error(f"Error listing negotiations: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics")
async def get_trading_analytics(
    period_type: str = Query(default="daily", description="Period type: daily, weekly, monthly"),
    start_date: Optional[str] = Query(default=None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(default=None, description="End date (ISO format)"),
    session: SessionDep
) -> Dict[str, Any]:
    """Get P2P trading analytics"""
    
    try:
        # Parse dates if provided
        start_dt = None
        end_dt = None
        if start_date:
            start_dt = datetime.fromisoformat(start_date)
        if end_date:
            end_dt = datetime.fromisoformat(end_date)
        
        if not start_dt:
            start_dt = datetime.utcnow() - timedelta(days=30)
        if not end_dt:
            end_dt = datetime.utcnow()
        
        # Get analytics data (mock implementation)
        # In real implementation, this would query TradingAnalytics table
        
        analytics = {
            "period_type": period_type,
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "total_trades": 150,
            "completed_trades": 120,
            "failed_trades": 15,
            "cancelled_trades": 15,
            "total_trade_volume": 7500.0,
            "average_trade_value": 50.0,
            "success_rate": 80.0,
            "trade_type_distribution": {
                "ai_power": 60,
                "compute_resources": 30,
                "data_services": 25,
                "model_services": 20,
                "inference_tasks": 15
            },
            "active_buyers": 45,
            "active_sellers": 38,
            "new_agents": 12,
            "average_matching_time": 15.5,  # minutes
            "average_negotiation_time": 45.2,  # minutes
            "average_settlement_time": 8.7,  # minutes
            "regional_distribution": {
                "us-east": 35,
                "us-west": 28,
                "eu-central": 22,
                "ap-southeast": 18,
                "ap-northeast": 15
            }
        }
        
        return analytics
        
    except Exception as e:
        logger.error(f"Error getting trading analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/simulate-match")
async def simulate_trade_matching(
    request_data: TradeRequestRequest,
    session: SessionDep
) -> Dict[str, Any]:
    """Simulate trade matching without creating actual request"""
    
    trading_protocol = P2PTradingProtocol(session)
    
    try:
        # Create temporary trade request for simulation
        temp_request = TradeRequest(
            request_id=f"sim_{uuid4().hex[:8]}",
            buyer_agent_id=request_data.buyer_agent_id,
            trade_type=request_data.trade_type,
            title=request_data.title,
            description=request_data.description,
            requirements=request_data.requirements,
            specifications=request_data.requirements.get('specifications', {}),
            budget_range=request_data.budget_range,
            preferred_regions=request_data.preferred_regions,
            excluded_regions=request_data.excluded_regions,
            service_level_required=request_data.service_level_required
        )
        
        # Get available sellers
        seller_offers = await trading_protocol.get_available_sellers(temp_request)
        seller_reputations = await trading_protocol.get_seller_reputations(
            [offer['agent_id'] for offer in seller_offers]
        )
        
        # Find matches
        matches = trading_protocol.matching_engine.find_matches(
            temp_request, seller_offers, seller_reputations
        )
        
        return {
            "simulation": True,
            "request_details": {
                "trade_type": request_data.trade_type.value,
                "budget_range": request_data.budget_range,
                "requirements": request_data.requirements
            },
            "available_sellers": len(seller_offers),
            "matches_found": len(matches),
            "best_matches": matches[:5],  # Top 5 matches
            "average_match_score": sum(m['match_score'] for m in matches) / len(matches) if matches else 0.0
        }
        
    except Exception as e:
        logger.error(f"Error simulating trade matching: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
