"""
Agent-to-Agent Trading Protocol Service
Implements P2P trading, matching, negotiation, and settlement systems
"""

import asyncio
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import uuid4
import json
from aitbc.logging import get_logger

from sqlmodel import Session, select, update, delete, and_, or_, func
from sqlalchemy.exc import SQLAlchemyError

from ..domain.trading import (
    TradeRequest, TradeMatch, TradeNegotiation, TradeAgreement, TradeSettlement,
    TradeFeedback, TradingAnalytics, TradeStatus, TradeType, NegotiationStatus,
    SettlementType
)
from ..domain.reputation import AgentReputation
from ..domain.rewards import AgentRewardProfile

logger = get_logger(__name__)


class MatchingEngine:
    """Advanced agent matching and routing algorithms"""
    
    def __init__(self):
        # Matching weights for different factors
        self.weights = {
            'price': 0.25,
            'specifications': 0.20,
            'timing': 0.15,
            'reputation': 0.15,
            'geography': 0.10,
            'availability': 0.10,
            'service_level': 0.05
        }
        
        # Matching thresholds
        self.min_match_score = 60.0  # Minimum score to consider a match
        self.max_matches_per_request = 10  # Maximum matches to return
        self.match_expiry_hours = 24  # Hours after which matches expire
    
    def calculate_price_compatibility(
        self, 
        buyer_budget: Dict[str, float], 
        seller_price: float
    ) -> float:
        """Calculate price compatibility score (0-100)"""
        
        min_budget = buyer_budget.get('min', 0)
        max_budget = buyer_budget.get('max', float('inf'))
        
        if seller_price < min_budget:
            return 0.0  # Below minimum budget
        elif seller_price > max_budget:
            return 0.0  # Above maximum budget
        else:
            # Calculate how well the price fits in the budget range
            if max_budget == float('inf'):
                return 100.0  # Any price above minimum is acceptable
            
            budget_range = max_budget - min_budget
            if budget_range == 0:
                return 100.0  # Exact price match
            
            price_position = (seller_price - min_budget) / budget_range
            # Prefer prices closer to middle of budget range
            center_preference = 1.0 - abs(price_position - 0.5) * 2
            return center_preference * 100.0
    
    def calculate_specification_compatibility(
        self, 
        buyer_specs: Dict[str, Any], 
        seller_specs: Dict[str, Any]
    ) -> float:
        """Calculate specification compatibility score (0-100)"""
        
        if not buyer_specs or not seller_specs:
            return 50.0  # Neutral score if specs not specified
        
        compatibility_scores = []
        
        # Check common specification keys
        common_keys = set(buyer_specs.keys()) & set(seller_specs.keys())
        
        for key in common_keys:
            buyer_value = buyer_specs[key]
            seller_value = seller_specs[key]
            
            if isinstance(buyer_value, (int, float)) and isinstance(seller_value, (int, float)):
                # Numeric comparison
                if buyer_value == seller_value:
                    score = 100.0
                elif buyer_value > seller_value:
                    # Buyer wants more than seller offers
                    score = max(0, 100 - (buyer_value - seller_value) / buyer_value * 100)
                else:
                    # Seller offers more than buyer wants (good)
                    score = 100.0
            elif isinstance(buyer_value, str) and isinstance(seller_value, str):
                # String comparison
                score = 100.0 if buyer_value.lower() == seller_value.lower() else 0.0
            elif isinstance(buyer_value, list) and isinstance(seller_value, list):
                # List comparison (intersection)
                buyer_set = set(buyer_value)
                seller_set = set(seller_value)
                intersection = buyer_set & seller_set
                if buyer_set:
                    score = len(intersection) / len(buyer_set) * 100.0
                else:
                    score = 0.0
            else:
                # Other types - exact match
                score = 100.0 if buyer_value == seller_value else 0.0
            
            compatibility_scores.append(score)
        
        if compatibility_scores:
            return sum(compatibility_scores) / len(compatibility_scores)
        else:
            return 50.0  # Neutral score if no common specs
    
    def calculate_timing_compatibility(
        self, 
        buyer_timing: Dict[str, Any], 
        seller_timing: Dict[str, Any]
    ) -> float:
        """Calculate timing compatibility score (0-100)"""
        
        buyer_start = buyer_timing.get('start_time')
        buyer_end = buyer_timing.get('end_time')
        seller_start = seller_timing.get('start_time')
        seller_end = seller_timing.get('end_time')
        
        if not buyer_start or not seller_start:
            return 80.0  # High score if timing not specified
        
        # Check for time overlap
        if buyer_end and seller_end:
            overlap = max(0, min(buyer_end, seller_end) - max(buyer_start, seller_start))
            total_time = min(buyer_end - buyer_start, seller_end - seller_start)
            
            if total_time > 0:
                return (overlap / total_time) * 100.0
            else:
                return 0.0
        else:
            # If end times not specified, check start time compatibility
            time_diff = abs((buyer_start - seller_start).total_seconds())
            hours_diff = time_diff / 3600
            
            if hours_diff <= 1:
                return 100.0
            elif hours_diff <= 6:
                return 80.0
            elif hours_diff <= 24:
                return 60.0
            else:
                return 40.0
    
    def calculate_reputation_compatibility(
        self, 
        buyer_reputation: float, 
        seller_reputation: float
    ) -> float:
        """Calculate reputation compatibility score (0-100)"""
        
        # Higher reputation scores for both parties result in higher compatibility
        avg_reputation = (buyer_reputation + seller_reputation) / 2
        
        # Normalize to 0-100 scale (assuming reputation is 0-1000)
        normalized_avg = min(100.0, avg_reputation / 10.0)
        
        return normalized_avg
    
    def calculate_geographic_compatibility(
        self, 
        buyer_regions: List[str], 
        seller_regions: List[str],
        buyer_excluded: List[str] = None,
        seller_excluded: List[str] = None
    ) -> float:
        """Calculate geographic compatibility score (0-100)"""
        
        buyer_excluded = buyer_excluded or []
        seller_excluded = seller_excluded or []
        
        # Check for excluded regions
        if seller_regions and any(region in buyer_excluded for region in seller_regions):
            return 0.0
        if buyer_regions and any(region in seller_excluded for region in buyer_regions):
            return 0.0
        
        # Check for preferred regions
        if buyer_regions and seller_regions:
            buyer_set = set(buyer_regions)
            seller_set = set(seller_regions)
            intersection = buyer_set & seller_set
            
            if buyer_set:
                return (len(intersection) / len(buyer_set)) * 100.0
            else:
                return 20.0  # Low score if no overlap
        elif buyer_regions or seller_regions:
            return 60.0  # Medium score if only one side specified
        else:
            return 80.0  # High score if neither side specified
    
    def calculate_overall_match_score(
        self, 
        buyer_request: TradeRequest, 
        seller_offer: Dict[str, Any],
        seller_reputation: float
    ) -> Dict[str, Any]:
        """Calculate overall match score with detailed breakdown"""
        
        # Extract seller details from offer
        seller_price = seller_offer.get('price', 0)
        seller_specs = seller_offer.get('specifications', {})
        seller_timing = seller_offer.get('timing', {})
        seller_regions = seller_offer.get('regions', [])
        
        # Calculate individual compatibility scores
        price_score = self.calculate_price_compatibility(
            buyer_request.budget_range, seller_price
        )
        
        spec_score = self.calculate_specification_compatibility(
            buyer_request.specifications, seller_specs
        )
        
        timing_score = self.calculate_timing_compatibility(
            buyer_request.requirements.get('timing', {}), seller_timing
        )
        
        # Get buyer reputation
        # This would typically come from the reputation service
        buyer_reputation = 500.0  # Default value
        
        reputation_score = self.calculate_reputation_compatibility(
            buyer_reputation, seller_reputation
        )
        
        geography_score = self.calculate_geographic_compatibility(
            buyer_request.preferred_regions, seller_regions,
            buyer_request.excluded_regions
        )
        
        # Calculate weighted overall score
        overall_score = (
            price_score * self.weights['price'] +
            spec_score * self.weights['specifications'] +
            timing_score * self.weights['timing'] +
            reputation_score * self.weights['reputation'] +
            geography_score * self.weights['geography']
        ) * 100  # Convert to 0-100 scale
        
        return {
            'overall_score': min(100.0, max(0.0, overall_score)),
            'price_compatibility': price_score,
            'specification_compatibility': spec_score,
            'timing_compatibility': timing_score,
            'reputation_compatibility': reputation_score,
            'geographic_compatibility': geography_score,
            'confidence_level': min(1.0, overall_score / 100.0)
        }
    
    def find_matches(
        self, 
        trade_request: TradeRequest, 
        seller_offers: List[Dict[str, Any]],
        seller_reputations: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Find best matching sellers for a trade request"""
        
        matches = []
        
        for seller_offer in seller_offers:
            seller_id = seller_offer.get('agent_id')
            seller_reputation = seller_reputations.get(seller_id, 500.0)
            
            # Calculate match score
            match_result = self.calculate_overall_match_score(
                trade_request, seller_offer, seller_reputation
            )
            
            # Only include matches above threshold
            if match_result['overall_score'] >= self.min_match_score:
                matches.append({
                    'seller_agent_id': seller_id,
                    'seller_offer': seller_offer,
                    'match_score': match_result['overall_score'],
                    'confidence_level': match_result['confidence_level'],
                    'compatibility_breakdown': match_result
                })
        
        # Sort by match score (descending)
        matches.sort(key=lambda x: x['match_score'], reverse=True)
        
        # Return top matches
        return matches[:self.max_matches_per_request]


class NegotiationSystem:
    """Automated negotiation system for trade agreements"""
    
    def __init__(self):
        # Negotiation strategies
        self.strategies = {
            'aggressive': {
                'price_tolerance': 0.05,  # 5% tolerance
                'concession_rate': 0.02,   # 2% per round
                'max_rounds': 3
            },
            'balanced': {
                'price_tolerance': 0.10,  # 10% tolerance
                'concession_rate': 0.05,   # 5% per round
                'max_rounds': 5
            },
            'cooperative': {
                'price_tolerance': 0.15,  # 15% tolerance
                'concession_rate': 0.08,   # 8% per round
                'max_rounds': 7
            }
        }
        
        # Negotiation timeouts
        self.response_timeout_minutes = 60  # Time to respond to offer
        self.max_negotiation_hours = 24    # Maximum negotiation duration
    
    def generate_initial_offer(
        self, 
        buyer_request: TradeRequest, 
        seller_offer: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate initial negotiation offer"""
        
        # Start with middle ground between buyer budget and seller price
        buyer_min = buyer_request.budget_range.get('min', 0)
        buyer_max = buyer_request.budget_range.get('max', float('inf'))
        seller_price = seller_offer.get('price', 0)
        
        if buyer_max == float('inf'):
            initial_price = (buyer_min + seller_price) / 2
        else:
            initial_price = (buyer_min + buyer_max + seller_price) / 3
        
        # Build initial offer
        initial_offer = {
            'price': initial_price,
            'specifications': self.merge_specifications(
                buyer_request.specifications, seller_offer.get('specifications', {})
            ),
            'timing': self.negotiate_timing(
                buyer_request.requirements.get('timing', {}),
                seller_offer.get('timing', {})
            ),
            'service_level': self.determine_service_level(
                buyer_request.service_level_required,
                seller_offer.get('service_level', 'standard')
            ),
            'payment_terms': {
                'settlement_type': 'escrow',
                'payment_schedule': 'milestone',
                'advance_payment': 0.2  # 20% advance
            },
            'delivery_terms': {
                'start_time': self.negotiate_start_time(
                    buyer_request.start_time,
                    seller_offer.get('timing', {}).get('start_time')
                ),
                'duration': self.negotiate_duration(
                    buyer_request.duration_hours,
                    seller_offer.get('timing', {}).get('duration_hours')
                )
            }
        }
        
        return initial_offer
    
    def merge_specifications(
        self, 
        buyer_specs: Dict[str, Any], 
        seller_specs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge buyer and seller specifications"""
        
        merged = {}
        
        # Start with buyer requirements
        for key, value in buyer_specs.items():
            merged[key] = value
        
        # Add seller capabilities that meet or exceed requirements
        for key, value in seller_specs.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(value, (int, float)) and isinstance(merged[key], (int, float)):
                # Use the higher value for capabilities
                merged[key] = max(merged[key], value)
        
        return merged
    
    def negotiate_timing(
        self, 
        buyer_timing: Dict[str, Any], 
        seller_timing: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Negotiate timing requirements"""
        
        negotiated = {}
        
        # Find common start time
        buyer_start = buyer_timing.get('start_time')
        seller_start = seller_timing.get('start_time')
        
        if buyer_start and seller_start:
            # Use the later start time
            negotiated['start_time'] = max(buyer_start, seller_start)
        elif buyer_start:
            negotiated['start_time'] = buyer_start
        elif seller_start:
            negotiated['start_time'] = seller_start
        
        # Negotiate duration
        buyer_duration = buyer_timing.get('duration_hours')
        seller_duration = seller_timing.get('duration_hours')
        
        if buyer_duration and seller_duration:
            negotiated['duration_hours'] = min(buyer_duration, seller_duration)
        elif buyer_duration:
            negotiated['duration_hours'] = buyer_duration
        elif seller_duration:
            negotiated['duration_hours'] = seller_duration
        
        return negotiated
    
    def determine_service_level(
        self, 
        buyer_required: str, 
        seller_offered: str
    ) -> str:
        """Determine appropriate service level"""
        
        levels = ['basic', 'standard', 'premium']
        
        # Use the higher service level
        if levels.index(buyer_required) > levels.index(seller_offered):
            return buyer_required
        else:
            return seller_offered
    
    def negotiate_start_time(
        self, 
        buyer_time: Optional[datetime], 
        seller_time: Optional[datetime]
    ) -> Optional[datetime]:
        """Negotiate start time"""
        
        if buyer_time and seller_time:
            return max(buyer_time, seller_time)
        elif buyer_time:
            return buyer_time
        elif seller_time:
            return seller_time
        else:
            return None
    
    def negotiate_duration(
        self, 
        buyer_duration: Optional[int], 
        seller_duration: Optional[int]
    ) -> Optional[int]:
        """Negotiate duration in hours"""
        
        if buyer_duration and seller_duration:
            return min(buyer_duration, seller_duration)
        elif buyer_duration:
            return buyer_duration
        elif seller_duration:
            return seller_duration
        else:
            return None
    
    def calculate_concession(
        self, 
        current_offer: Dict[str, Any], 
        previous_offer: Dict[str, Any],
        strategy: str,
        round_number: int
    ) -> Dict[str, Any]:
        """Calculate concession based on negotiation strategy"""
        
        strategy_config = self.strategies.get(strategy, self.strategies['balanced'])
        concession_rate = strategy_config['concession_rate']
        
        # Calculate concession amount
        if 'price' in current_offer and 'price' in previous_offer:
            price_diff = previous_offer['price'] - current_offer['price']
            concession = price_diff * concession_rate
            
            new_offer = current_offer.copy()
            new_offer['price'] = current_offer['price'] + concession
            
            return new_offer
        
        return current_offer
    
    def evaluate_offer(
        self, 
        offer: Dict[str, Any], 
        requirements: Dict[str, Any],
        strategy: str
    ) -> Dict[str, Any]:
        """Evaluate if an offer should be accepted"""
        
        strategy_config = self.strategies.get(strategy, self.strategies['balanced'])
        price_tolerance = strategy_config['price_tolerance']
        
        # Check price against budget
        if 'price' in offer and 'budget_range' in requirements:
            budget_min = requirements['budget_range'].get('min', 0)
            budget_max = requirements['budget_range'].get('max', float('inf'))
            
            if offer['price'] < budget_min:
                return {'should_accept': False, 'reason': 'price_below_minimum'}
            elif budget_max != float('inf') and offer['price'] > budget_max:
                return {'should_accept': False, 'reason': 'price_above_maximum'}
            
            # Check if price is within tolerance
            if budget_max != float('inf'):
                price_position = (offer['price'] - budget_min) / (budget_max - budget_min)
                if price_position <= (1.0 - price_tolerance):
                    return {'should_accept': True, 'reason': 'price_within_tolerance'}
        
        # Check other requirements
        if 'specifications' in offer and 'specifications' in requirements:
            spec_compatibility = self.calculate_spec_compatibility(
                requirements['specifications'], offer['specifications']
            )
            
            if spec_compatibility < 70.0:  # 70% minimum spec compatibility
                return {'should_accept': False, 'reason': 'specifications_incompatible'}
        
        return {'should_accept': True, 'reason': 'acceptable_offer'}
    
    def calculate_spec_compatibility(
        self, 
        required_specs: Dict[str, Any], 
        offered_specs: Dict[str, Any]
    ) -> float:
        """Calculate specification compatibility (reused from matching engine)"""
        
        if not required_specs or not offered_specs:
            return 50.0
        
        compatibility_scores = []
        common_keys = set(required_specs.keys()) & set(offered_specs.keys())
        
        for key in common_keys:
            required_value = required_specs[key]
            offered_value = offered_specs[key]
            
            if isinstance(required_value, (int, float)) and isinstance(offered_value, (int, float)):
                if offered_value >= required_value:
                    score = 100.0
                else:
                    score = (offered_value / required_value) * 100.0
            else:
                score = 100.0 if str(required_value).lower() == str(offered_value).lower() else 0.0
            
            compatibility_scores.append(score)
        
        return sum(compatibility_scores) / len(compatibility_scores) if compatibility_scores else 50.0


class SettlementLayer:
    """Secure settlement and escrow system"""
    
    def __init__(self):
        # Settlement configurations
        self.settlement_types = {
            'immediate': {
                'requires_escrow': False,
                'processing_time': 0,  # minutes
                'fee_rate': 0.01  # 1%
            },
            'escrow': {
                'requires_escrow': True,
                'processing_time': 5,  # minutes
                'fee_rate': 0.02  # 2%
            },
            'milestone': {
                'requires_escrow': True,
                'processing_time': 10,  # minutes
                'fee_rate': 0.025  # 2.5%
            },
            'subscription': {
                'requires_escrow': False,
                'processing_time': 2,  # minutes
                'fee_rate': 0.015  # 1.5%
            }
        }
        
        # Escrow configurations
        self.escrow_release_conditions = {
            'delivery_confirmed': {
                'requires_buyer_confirmation': True,
                'requires_seller_confirmation': False,
                'auto_release_delay_hours': 24
            },
            'milestone_completed': {
                'requires_buyer_confirmation': True,
                'requires_seller_confirmation': True,
                'auto_release_delay_hours': 2
            },
            'time_based': {
                'requires_buyer_confirmation': False,
                'requires_seller_confirmation': False,
                'auto_release_delay_hours': 168  # 1 week
            }
        }
    
    def create_settlement(
        self, 
        agreement: TradeAgreement,
        settlement_type: SettlementType
    ) -> Dict[str, Any]:
        """Create settlement configuration"""
        
        config = self.settlement_types.get(settlement_type, self.settlement_types['escrow'])
        
        settlement = {
            'settlement_id': f"settle_{uuid4().hex[:8]}",
            'agreement_id': agreement.agreement_id,
            'settlement_type': settlement_type,
            'total_amount': agreement.total_price,
            'currency': agreement.currency,
            'requires_escrow': config['requires_escrow'],
            'processing_time_minutes': config['processing_time'],
            'fee_rate': config['fee_rate'],
            'platform_fee': agreement.total_price * config['fee_rate'],
            'net_amount_seller': agreement.total_price * (1 - config['fee_rate'])
        }
        
        # Add escrow configuration if required
        if config['requires_escrow']:
            settlement['escrow_config'] = {
                'escrow_address': self.generate_escrow_address(),
                'release_conditions': agreement.service_level_agreement.get('escrow_conditions', {}),
                'auto_release': True,
                'dispute_resolution_enabled': True
            }
        
        # Add milestone configuration if applicable
        if settlement_type == SettlementType.MILESTONE:
            settlement['milestone_config'] = {
                'milestones': agreement.payment_schedule.get('milestones', []),
                'release_triggers': agreement.delivery_timeline.get('milestone_triggers', {})
            }
        
        # Add subscription configuration if applicable
        if settlement_type == SettlementType.SUBSCRIPTION:
            settlement['subscription_config'] = {
                'billing_cycle': agreement.payment_schedule.get('billing_cycle', 'monthly'),
                'auto_renewal': agreement.payment_schedule.get('auto_renewal', True),
                'cancellation_policy': agreement.terms_and_conditions.get('cancellation_policy', {})
            }
        
        return settlement
    
    def generate_escrow_address(self) -> str:
        """Generate unique escrow address"""
        return f"0x{uuid4().hex}"
    
    def process_payment(
        self, 
        settlement: Dict[str, Any],
        payment_method: str = "blockchain"
    ) -> Dict[str, Any]:
        """Process payment through settlement layer"""
        
        # Simulate blockchain transaction
        transaction_id = f"tx_{uuid4().hex[:8]}"
        transaction_hash = f"0x{uuid4().hex}"
        
        payment_result = {
            'transaction_id': transaction_id,
            'transaction_hash': transaction_hash,
            'status': 'processing',
            'payment_method': payment_method,
            'amount': settlement['total_amount'],
            'currency': settlement['currency'],
            'fee': settlement['platform_fee'],
            'net_amount': settlement['net_amount_seller'],
            'processed_at': datetime.utcnow().isoformat()
        }
        
        # Add escrow details if applicable
        if settlement['requires_escrow']:
            payment_result['escrow_address'] = settlement['escrow_config']['escrow_address']
            payment_result['escrow_status'] = 'locked'
        
        return payment_result
    
    def release_escrow(
        self, 
        settlement: Dict[str, Any],
        release_reason: str,
        release_conditions_met: bool = True
    ) -> Dict[str, Any]:
        """Release funds from escrow"""
        
        if not settlement['requires_escrow']:
            return {'error': 'Settlement does not require escrow'}
        
        release_result = {
            'settlement_id': settlement['settlement_id'],
            'escrow_address': settlement['escrow_config']['escrow_address'],
            'release_reason': release_reason,
            'conditions_met': release_conditions_met,
            'released_at': datetime.utcnow().isoformat(),
            'status': 'released' if release_conditions_met else 'held'
        }
        
        if release_conditions_met:
            release_result['transaction_id'] = f"release_{uuid4().hex[:8]}"
            release_result['amount_released'] = settlement['net_amount_seller']
        else:
            release_result['hold_reason'] = 'Release conditions not met'
        
        return release_result
    
    def handle_dispute(
        self, 
        settlement: Dict[str, Any],
        dispute_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle dispute resolution for settlement"""
        
        dispute_result = {
            'settlement_id': settlement['settlement_id'],
            'dispute_id': f"dispute_{uuid4().hex[:8]}",
            'dispute_type': dispute_details.get('type', 'general'),
            'dispute_reason': dispute_details.get('reason', ''),
            'initiated_by': dispute_details.get('initiated_by', ''),
            'initiated_at': datetime.utcnow().isoformat(),
            'status': 'under_review'
        }
        
        # Add escrow hold if applicable
        if settlement['requires_escrow']:
            dispute_result['escrow_status'] = 'held_pending_resolution'
            dispute_result['escrow_release_blocked'] = True
        
        return dispute_result


class P2PTradingProtocol:
    """Main P2P trading protocol service"""
    
    def __init__(self, session: Session):
        self.session = session
        self.matching_engine = MatchingEngine()
        self.negotiation_system = NegotiationSystem()
        self.settlement_layer = SettlementLayer()
    
    async def create_trade_request(
        self,
        buyer_agent_id: str,
        trade_type: TradeType,
        title: str,
        description: str,
        requirements: Dict[str, Any],
        budget_range: Dict[str, float],
        **kwargs
    ) -> TradeRequest:
        """Create a new trade request"""
        
        trade_request = TradeRequest(
            request_id=f"req_{uuid4().hex[:8]}",
            buyer_agent_id=buyer_agent_id,
            trade_type=trade_type,
            title=title,
            description=description,
            requirements=requirements,
            specifications=requirements.get('specifications', {}),
            constraints=requirements.get('constraints', {}),
            budget_range=budget_range,
            preferred_terms=requirements.get('preferred_terms', {}),
            start_time=kwargs.get('start_time'),
            end_time=kwargs.get('end_time'),
            duration_hours=kwargs.get('duration_hours'),
            urgency_level=kwargs.get('urgency_level', 'normal'),
            preferred_regions=kwargs.get('preferred_regions', []),
            excluded_regions=kwargs.get('excluded_regions', []),
            service_level_required=kwargs.get('service_level_required', 'standard'),
            tags=kwargs.get('tags', []),
            metadata=kwargs.get('metadata', {}),
            expires_at=kwargs.get('expires_at', datetime.utcnow() + timedelta(days=7))
        )
        
        self.session.add(trade_request)
        self.session.commit()
        self.session.refresh(trade_request)
        
        logger.info(f"Created trade request {trade_request.request_id} for agent {buyer_agent_id}")
        return trade_request
    
    async def find_matches(self, request_id: str) -> List[Dict[str, Any]]:
        """Find matching sellers for a trade request"""
        
        # Get trade request
        trade_request = self.session.execute(
            select(TradeRequest).where(TradeRequest.request_id == request_id)
        ).first()
        
        if not trade_request:
            raise ValueError(f"Trade request {request_id} not found")
        
        # Get available sellers (mock implementation)
        # In real implementation, this would query available seller offers
        seller_offers = await self.get_available_sellers(trade_request)
        
        # Get seller reputations
        seller_ids = [offer['agent_id'] for offer in seller_offers]
        seller_reputations = await self.get_seller_reputations(seller_ids)
        
        # Find matches using matching engine
        matches = self.matching_engine.find_matches(
            trade_request, seller_offers, seller_reputations
        )
        
        # Create trade match records
        trade_matches = []
        for match in matches:
            trade_match = TradeMatch(
                match_id=f"match_{uuid4().hex[:8]}",
                request_id=request_id,
                buyer_agent_id=trade_request.buyer_agent_id,
                seller_agent_id=match['seller_agent_id'],
                match_score=match['match_score'],
                confidence_level=match['confidence_level'],
                price_compatibility=match['compatibility_breakdown']['price_compatibility'],
                timing_compatibility=match['compatibility_breakdown']['timing_compatibility'],
                specification_compatibility=match['compatibility_breakdown']['specification_compatibility'],
                reputation_compatibility=match['compatibility_breakdown']['reputation_compatibility'],
                geographic_compatibility=match['compatibility_breakdown']['geographic_compatibility'],
                seller_offer=match['seller_offer'],
                proposed_terms=match['seller_offer'].get('terms', {}),
                expires_at=datetime.utcnow() + timedelta(hours=self.matching_engine.match_expiry_hours)
            )
            
            self.session.add(trade_match)
            trade_matches.append(trade_match)
        
        self.session.commit()
        
        # Update request match count
        trade_request.match_count = len(trade_matches)
        trade_request.best_match_score = matches[0]['match_score'] if matches else 0.0
        trade_request.updated_at = datetime.utcnow()
        self.session.commit()
        
        logger.info(f"Found {len(trade_matches)} matches for request {request_id}")
        return [match['seller_agent_id'] for match in matches]
    
    async def initiate_negotiation(
        self,
        match_id: str,
        initiator: str,  # buyer or seller
        strategy: str = "balanced"
    ) -> TradeNegotiation:
        """Initiate negotiation between buyer and seller"""
        
        # Get trade match
        trade_match = self.session.execute(
            select(TradeMatch).where(TradeMatch.match_id == match_id)
        ).first()
        
        if not trade_match:
            raise ValueError(f"Trade match {match_id} not found")
        
        # Get trade request
        trade_request = self.session.execute(
            select(TradeRequest).where(TradeRequest.request_id == trade_match.request_id)
        ).first()
        
        # Generate initial offer
        initial_offer = self.negotiation_system.generate_initial_offer(
            trade_request, trade_match.seller_offer
        )
        
        # Create negotiation record
        negotiation = TradeNegotiation(
            negotiation_id=f"neg_{uuid4().hex[:8]}",
            match_id=match_id,
            buyer_agent_id=trade_match.buyer_agent_id,
            seller_agent_id=trade_match.seller_agent_id,
            status=NegotiationStatus.PENDING,
            negotiation_strategy=strategy,
            current_terms=initial_offer,
            initial_terms=initial_offer,
            auto_accept_threshold=85.0,
            started_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=self.negotiation_system.max_negotiation_hours)
        )
        
        self.session.add(negotiation)
        self.session.commit()
        self.session.refresh(negotiation)
        
        # Update match status
        trade_match.status = TradeStatus.NEGOTIATING
        trade_match.negotiation_initiated = True
        trade_match.negotiation_initiator = initiator
        trade_match.initial_terms = initial_offer
        trade_match.last_interaction = datetime.utcnow()
        self.session.commit()
        
        logger.info(f"Initiated negotiation {negotiation.negotiation_id} for match {match_id}")
        return negotiation
    
    async def get_available_sellers(self, trade_request: TradeRequest) -> List[Dict[str, Any]]:
        """Get available sellers for a trade request (mock implementation)"""
        
        # This would typically query the marketplace for available sellers
        # For now, return mock seller offers
        mock_sellers = [
            {
                'agent_id': 'seller_001',
                'price': 0.05,
                'specifications': {'cpu_cores': 4, 'memory_gb': 16, 'gpu_count': 1},
                'timing': {'start_time': datetime.utcnow(), 'duration_hours': 8},
                'regions': ['us-east', 'us-west'],
                'service_level': 'premium',
                'terms': {'settlement_type': 'escrow', 'delivery_guarantee': True}
            },
            {
                'agent_id': 'seller_002',
                'price': 0.045,
                'specifications': {'cpu_cores': 2, 'memory_gb': 8, 'gpu_count': 1},
                'timing': {'start_time': datetime.utcnow(), 'duration_hours': 6},
                'regions': ['us-east'],
                'service_level': 'standard',
                'terms': {'settlement_type': 'immediate', 'delivery_guarantee': False}
            }
        ]
        
        return mock_sellers
    
    async def get_seller_reputations(self, seller_ids: List[str]) -> Dict[str, float]:
        """Get seller reputations (mock implementation)"""
        
        # This would typically query the reputation service
        # For now, return mock reputations
        mock_reputations = {
            'seller_001': 750.0,
            'seller_002': 650.0
        }
        
        return {seller_id: mock_reputations.get(seller_id, 500.0) for seller_id in seller_ids}
    
    async def get_trading_summary(self, agent_id: str) -> Dict[str, Any]:
        """Get comprehensive trading summary for an agent"""
        
        # Get trade requests
        requests = self.session.execute(
            select(TradeRequest).where(TradeRequest.buyer_agent_id == agent_id)
        ).all()
        
        # Get trade matches
        matches = self.session.execute(
            select(TradeMatch).where(
                or_(
                    TradeMatch.buyer_agent_id == agent_id,
                    TradeMatch.seller_agent_id == agent_id
                )
            )
        ).all()
        
        # Get negotiations
        negotiations = self.session.execute(
            select(TradeNegotiation).where(
                or_(
                    TradeNegotiation.buyer_agent_id == agent_id,
                    TradeNegotiation.seller_agent_id == agent_id
                )
            )
        ).all()
        
        # Get agreements
        agreements = self.session.execute(
            select(TradeAgreement).where(
                or_(
                    TradeAgreement.buyer_agent_id == agent_id,
                    TradeAgreement.seller_agent_id == agent_id
                )
            )
        ).all()
        
        return {
            'agent_id': agent_id,
            'trade_requests': len(requests),
            'trade_matches': len(matches),
            'negotiations': len(negotiations),
            'agreements': len(agreements),
            'success_rate': len(agreements) / len(matches) if matches else 0.0,
            'average_match_score': sum(m.match_score for m in matches) / len(matches) if matches else 0.0,
            'total_trade_volume': sum(a.total_price for a in agreements),
            'recent_activity': {
                'requests_last_30d': len([r for r in requests if r.created_at >= datetime.utcnow() - timedelta(days=30)]),
                'matches_last_30d': len([m for m in matches if m.created_at >= datetime.utcnow() - timedelta(days=30)]),
                'agreements_last_30d': len([a for a in agreements if a.created_at >= datetime.utcnow() - timedelta(days=30)])
            }
        }
