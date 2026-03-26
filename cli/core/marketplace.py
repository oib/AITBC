"""
Global chain marketplace system
"""

import asyncio
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from enum import Enum
import uuid
from decimal import Decimal
from collections import defaultdict

from core.config import MultiChainConfig
from core.node_client import NodeClient

class ChainType(Enum):
    """Chain types in marketplace"""
    TOPIC = "topic"
    PRIVATE = "private"
    RESEARCH = "research"
    ENTERPRISE = "enterprise"
    GOVERNANCE = "governance"

class MarketplaceStatus(Enum):
    """Marketplace listing status"""
    ACTIVE = "active"
    PENDING = "pending"
    SOLD = "sold"
    EXPIRED = "expired"
    DELISTED = "delisted"

class TransactionStatus(Enum):
    """Transaction status"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

@dataclass
class ChainListing:
    """Chain marketplace listing"""
    listing_id: str
    chain_id: str
    chain_name: str
    chain_type: ChainType
    description: str
    seller_id: str
    price: Decimal
    currency: str
    status: MarketplaceStatus
    created_at: datetime
    expires_at: datetime
    metadata: Dict[str, Any]
    chain_specifications: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    reputation_requirements: Dict[str, Any]
    governance_rules: Dict[str, Any]

@dataclass
class MarketplaceTransaction:
    """Marketplace transaction"""
    transaction_id: str
    listing_id: str
    buyer_id: str
    seller_id: str
    chain_id: str
    price: Decimal
    currency: str
    status: TransactionStatus
    created_at: datetime
    completed_at: Optional[datetime]
    escrow_address: str
    smart_contract_address: str
    transaction_hash: Optional[str]
    metadata: Dict[str, Any]

@dataclass
class ChainEconomy:
    """Chain economic metrics"""
    chain_id: str
    total_value_locked: Decimal
    daily_volume: Decimal
    market_cap: Decimal
    price_history: List[Dict[str, Any]]
    transaction_count: int
    active_users: int
    agent_count: int
    governance_tokens: Decimal
    staking_rewards: Decimal
    last_updated: datetime

@dataclass
class MarketplaceMetrics:
    """Marketplace performance metrics"""
    total_listings: int
    active_listings: int
    total_transactions: int
    total_volume: Decimal
    average_price: Decimal
    popular_chain_types: Dict[str, int]
    top_sellers: List[Dict[str, Any]]
    price_trends: Dict[str, List[Decimal]]
    market_sentiment: float
    last_updated: datetime

class GlobalChainMarketplace:
    """Global chain marketplace system"""
    
    def __init__(self, config: MultiChainConfig):
        self.config = config
        self.listings: Dict[str, ChainListing] = {}
        self.transactions: Dict[str, MarketplaceTransaction] = {}
        self.chain_economies: Dict[str, ChainEconomy] = {}
        self.user_reputations: Dict[str, float] = {}
        self.market_metrics: Optional[MarketplaceMetrics] = None
        self.escrow_contracts: Dict[str, Dict[str, Any]] = {}
        self.price_history: Dict[str, List[Decimal]] = defaultdict(list)
        
        # Marketplace thresholds
        self.thresholds = {
            'min_reputation_score': 0.5,
            'max_listing_duration_days': 30,
            'escrow_fee_percentage': 0.02,  # 2%
            'marketplace_fee_percentage': 0.01,  # 1%
            'min_chain_price': Decimal('0.001'),
            'max_chain_price': Decimal('1000000')
        }
    
    async def create_listing(self, chain_id: str, chain_name: str, chain_type: ChainType,
                           description: str, seller_id: str, price: Decimal, currency: str,
                           chain_specifications: Dict[str, Any], metadata: Dict[str, Any]) -> Optional[str]:
        """Create a new chain listing in the marketplace"""
        try:
            # Validate seller reputation
            if self.user_reputations.get(seller_id, 0) < self.thresholds['min_reputation_score']:
                return None
            
            # Validate price
            if price < self.thresholds['min_chain_price'] or price > self.thresholds['max_chain_price']:
                return None
            
            # Check if chain already has active listing
            for listing in self.listings.values():
                if listing.chain_id == chain_id and listing.status == MarketplaceStatus.ACTIVE:
                    return None
            
            # Create listing
            listing_id = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(days=self.thresholds['max_listing_duration_days'])
            
            listing = ChainListing(
                listing_id=listing_id,
                chain_id=chain_id,
                chain_name=chain_name,
                chain_type=chain_type,
                description=description,
                seller_id=seller_id,
                price=price,
                currency=currency,
                status=MarketplaceStatus.ACTIVE,
                created_at=datetime.now(),
                expires_at=expires_at,
                metadata=metadata,
                chain_specifications=chain_specifications,
                performance_metrics={},
                reputation_requirements={"min_score": 0.5},
                governance_rules={"voting_threshold": 0.6}
            )
            
            self.listings[listing_id] = listing
            
            # Update price history
            self.price_history[chain_id].append(price)
            
            # Update market metrics
            await self._update_market_metrics()
            
            return listing_id
            
        except Exception as e:
            print(f"Error creating listing: {e}")
            return None
    
    async def purchase_chain(self, listing_id: str, buyer_id: str, payment_method: str) -> Optional[str]:
        """Purchase a chain from the marketplace"""
        try:
            listing = self.listings.get(listing_id)
            if not listing or listing.status != MarketplaceStatus.ACTIVE:
                return None
            
            # Validate buyer reputation
            if self.user_reputations.get(buyer_id, 0) < self.thresholds['min_reputation_score']:
                return None
            
            # Check if listing is expired
            if datetime.now() > listing.expires_at:
                listing.status = MarketplaceStatus.EXPIRED
                return None
            
            # Create transaction
            transaction_id = str(uuid.uuid4())
            escrow_address = f"escrow_{transaction_id[:8]}"
            smart_contract_address = f"contract_{transaction_id[:8]}"
            
            transaction = MarketplaceTransaction(
                transaction_id=transaction_id,
                listing_id=listing_id,
                buyer_id=buyer_id,
                seller_id=listing.seller_id,
                chain_id=listing.chain_id,
                price=listing.price,
                currency=listing.currency,
                status=TransactionStatus.PENDING,
                created_at=datetime.now(),
                completed_at=None,
                escrow_address=escrow_address,
                smart_contract_address=smart_contract_address,
                transaction_hash=None,
                metadata={"payment_method": payment_method}
            )
            
            self.transactions[transaction_id] = transaction
            
            # Create escrow contract
            await self._create_escrow_contract(transaction)
            
            # Update listing status
            listing.status = MarketplaceStatus.SOLD
            
            # Update market metrics
            await self._update_market_metrics()
            
            return transaction_id
            
        except Exception as e:
            print(f"Error purchasing chain: {e}")
            return None
    
    async def complete_transaction(self, transaction_id: str, transaction_hash: str) -> bool:
        """Complete a marketplace transaction"""
        try:
            transaction = self.transactions.get(transaction_id)
            if not transaction or transaction.status != TransactionStatus.PENDING:
                return False
            
            # Update transaction
            transaction.status = TransactionStatus.COMPLETED
            transaction.completed_at = datetime.now()
            transaction.transaction_hash = transaction_hash
            
            # Release escrow
            await self._release_escrow(transaction)
            
            # Update reputations
            self._update_user_reputation(transaction.buyer_id, 0.1)  # Positive update
            self._update_user_reputation(transaction.seller_id, 0.1)
            
            # Update chain economy
            await self._update_chain_economy(transaction.chain_id, transaction.price)
            
            # Update market metrics
            await self._update_market_metrics()
            
            return True
            
        except Exception as e:
            print(f"Error completing transaction: {e}")
            return False
    
    async def get_chain_economy(self, chain_id: str) -> Optional[ChainEconomy]:
        """Get economic metrics for a specific chain"""
        try:
            if chain_id not in self.chain_economies:
                # Initialize chain economy
                self.chain_economies[chain_id] = ChainEconomy(
                    chain_id=chain_id,
                    total_value_locked=Decimal('0'),
                    daily_volume=Decimal('0'),
                    market_cap=Decimal('0'),
                    price_history=[],
                    transaction_count=0,
                    active_users=0,
                    agent_count=0,
                    governance_tokens=Decimal('0'),
                    staking_rewards=Decimal('0'),
                    last_updated=datetime.now()
                )
            
            # Update with latest data
            await self._update_chain_economy(chain_id)
            
            return self.chain_economies[chain_id]
            
        except Exception as e:
            print(f"Error getting chain economy: {e}")
            return None
    
    async def search_listings(self, chain_type: Optional[ChainType] = None,
                           min_price: Optional[Decimal] = None,
                           max_price: Optional[Decimal] = None,
                           seller_id: Optional[str] = None,
                           status: Optional[MarketplaceStatus] = None) -> List[ChainListing]:
        """Search chain listings with filters"""
        try:
            results = []
            
            for listing in self.listings.values():
                # Apply filters
                if chain_type and listing.chain_type != chain_type:
                    continue
                
                if min_price and listing.price < min_price:
                    continue
                
                if max_price and listing.price > max_price:
                    continue
                
                if seller_id and listing.seller_id != seller_id:
                    continue
                
                if status and listing.status != status:
                    continue
                
                results.append(listing)
            
            # Sort by creation date (newest first)
            results.sort(key=lambda x: x.created_at, reverse=True)
            
            return results
            
        except Exception as e:
            print(f"Error searching listings: {e}")
            return []
    
    async def get_user_transactions(self, user_id: str, role: str = "both") -> List[MarketplaceTransaction]:
        """Get transactions for a specific user"""
        try:
            results = []
            
            for transaction in self.transactions.values():
                if role == "buyer" and transaction.buyer_id != user_id:
                    continue
                
                if role == "seller" and transaction.seller_id != user_id:
                    continue
                
                if role == "both" and transaction.buyer_id != user_id and transaction.seller_id != user_id:
                    continue
                
                results.append(transaction)
            
            # Sort by creation date (newest first)
            results.sort(key=lambda x: x.created_at, reverse=True)
            
            return results
            
        except Exception as e:
            print(f"Error getting user transactions: {e}")
            return []
    
    async def get_marketplace_overview(self) -> Dict[str, Any]:
        """Get comprehensive marketplace overview"""
        try:
            await self._update_market_metrics()
            
            if not self.market_metrics:
                return {}
            
            # Calculate additional metrics
            total_volume_24h = await self._calculate_24h_volume()
            top_chains = await self._get_top_performing_chains()
            price_trends = await self._calculate_price_trends()
            
            overview = {
                "marketplace_metrics": asdict(self.market_metrics),
                "volume_24h": total_volume_24h,
                "top_performing_chains": top_chains,
                "price_trends": price_trends,
                "chain_types_distribution": await self._get_chain_types_distribution(),
                "user_activity": await self._get_user_activity_metrics(),
                "escrow_summary": await self._get_escrow_summary()
            }
            
            return overview
            
        except Exception as e:
            print(f"Error getting marketplace overview: {e}")
            return {}
    
    async def _create_escrow_contract(self, transaction: MarketplaceTransaction):
        """Create escrow contract for transaction"""
        try:
            escrow_contract = {
                "contract_address": transaction.escrow_address,
                "transaction_id": transaction.transaction_id,
                "amount": transaction.price,
                "currency": transaction.currency,
                "buyer_id": transaction.buyer_id,
                "seller_id": transaction.seller_id,
                "created_at": datetime.now(),
                "status": "active",
                "release_conditions": {
                    "transaction_confirmed": False,
                    "dispute_resolved": False
                }
            }
            
            self.escrow_contracts[transaction.escrow_address] = escrow_contract
            
        except Exception as e:
            print(f"Error creating escrow contract: {e}")
    
    async def _release_escrow(self, transaction: MarketplaceTransaction):
        """Release escrow funds"""
        try:
            escrow_contract = self.escrow_contracts.get(transaction.escrow_address)
            if escrow_contract:
                escrow_contract["status"] = "released"
                escrow_contract["released_at"] = datetime.now()
                escrow_contract["release_conditions"]["transaction_confirmed"] = True
                
                # Calculate fees
                escrow_fee = transaction.price * Decimal(str(self.thresholds['escrow_fee_percentage']))
                marketplace_fee = transaction.price * Decimal(str(self.thresholds['marketplace_fee_percentage']))
                seller_amount = transaction.price - escrow_fee - marketplace_fee
                
                escrow_contract["fee_breakdown"] = {
                    "escrow_fee": escrow_fee,
                    "marketplace_fee": marketplace_fee,
                    "seller_amount": seller_amount
                }
                
        except Exception as e:
            print(f"Error releasing escrow: {e}")
    
    async def _update_chain_economy(self, chain_id: str, transaction_price: Optional[Decimal] = None):
        """Update chain economic metrics"""
        try:
            if chain_id not in self.chain_economies:
                self.chain_economies[chain_id] = ChainEconomy(
                    chain_id=chain_id,
                    total_value_locked=Decimal('0'),
                    daily_volume=Decimal('0'),
                    market_cap=Decimal('0'),
                    price_history=[],
                    transaction_count=0,
                    active_users=0,
                    agent_count=0,
                    governance_tokens=Decimal('0'),
                    staking_rewards=Decimal('0'),
                    last_updated=datetime.now()
                )
            
            economy = self.chain_economies[chain_id]
            
            # Update with transaction price if provided
            if transaction_price:
                economy.daily_volume += transaction_price
                economy.transaction_count += 1
                
                # Add to price history
                economy.price_history.append({
                    "price": float(transaction_price),
                    "timestamp": datetime.now().isoformat(),
                    "volume": float(transaction_price)
                })
            
            # Update other metrics (would be fetched from chain nodes)
            # For now, using mock data
            economy.active_users = max(10, economy.active_users)
            economy.agent_count = max(5, economy.agent_count)
            economy.total_value_locked = economy.daily_volume * Decimal('10')  # Mock TVL
            economy.market_cap = economy.daily_volume * Decimal('100')  # Mock market cap
            
            economy.last_updated = datetime.now()
            
        except Exception as e:
            print(f"Error updating chain economy: {e}")
    
    async def _update_market_metrics(self):
        """Update marketplace performance metrics"""
        try:
            total_listings = len(self.listings)
            active_listings = len([l for l in self.listings.values() if l.status == MarketplaceStatus.ACTIVE])
            total_transactions = len(self.transactions)
            
            # Calculate total volume and average price
            completed_transactions = [t for t in self.transactions.values() if t.status == TransactionStatus.COMPLETED]
            total_volume = sum(t.price for t in completed_transactions)
            average_price = total_volume / len(completed_transactions) if completed_transactions else Decimal('0')
            
            # Popular chain types
            chain_types = defaultdict(int)
            for listing in self.listings.values():
                chain_types[listing.chain_type.value] += 1
            
            # Top sellers
            seller_stats = defaultdict(lambda: {"count": 0, "volume": Decimal('0')})
            for transaction in completed_transactions:
                seller_stats[transaction.seller_id]["count"] += 1
                seller_stats[transaction.seller_id]["volume"] += transaction.price
            
            top_sellers = [
                {"seller_id": seller_id, "sales_count": stats["count"], "total_volume": float(stats["volume"])}
                for seller_id, stats in seller_stats.items()
            ]
            top_sellers.sort(key=lambda x: x["total_volume"], reverse=True)
            top_sellers = top_sellers[:10]  # Top 10
            
            # Price trends
            price_trends = {}
            for chain_id, prices in self.price_history.items():
                if len(prices) >= 2:
                    trend = (prices[-1] - prices[-2]) / prices[-2] if prices[-2] != 0 else 0
                    price_trends[chain_id] = [trend]
            
            # Market sentiment (mock calculation)
            market_sentiment = 0.5  # Neutral
            if completed_transactions:
                positive_ratio = len(completed_transactions) / max(1, total_transactions)
                market_sentiment = min(1.0, positive_ratio * 1.2)
            
            self.market_metrics = MarketplaceMetrics(
                total_listings=total_listings,
                active_listings=active_listings,
                total_transactions=total_transactions,
                total_volume=total_volume,
                average_price=average_price,
                popular_chain_types=dict(chain_types),
                top_sellers=top_sellers,
                price_trends=price_trends,
                market_sentiment=market_sentiment,
                last_updated=datetime.now()
            )
            
        except Exception as e:
            print(f"Error updating market metrics: {e}")
    
    def _update_user_reputation(self, user_id: str, delta: float):
        """Update user reputation"""
        try:
            current_rep = self.user_reputations.get(user_id, 0.5)
            new_rep = max(0.0, min(1.0, current_rep + delta))
            self.user_reputations[user_id] = new_rep
        except Exception as e:
            print(f"Error updating user reputation: {e}")
    
    async def _calculate_24h_volume(self) -> Decimal:
        """Calculate 24-hour trading volume"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)
            recent_transactions = [
                t for t in self.transactions.values()
                if t.created_at >= cutoff_time and t.status == TransactionStatus.COMPLETED
            ]
            
            return sum(t.price for t in recent_transactions)
        except Exception as e:
            print(f"Error calculating 24h volume: {e}")
            return Decimal('0')
    
    async def _get_top_performing_chains(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top performing chains by volume"""
        try:
            chain_performance = defaultdict(lambda: {"volume": Decimal('0'), "transactions": 0})
            
            for transaction in self.transactions.values():
                if transaction.status == TransactionStatus.COMPLETED:
                    chain_performance[transaction.chain_id]["volume"] += transaction.price
                    chain_performance[transaction.chain_id]["transactions"] += 1
            
            top_chains = [
                {
                    "chain_id": chain_id,
                    "volume": float(stats["volume"]),
                    "transactions": stats["transactions"]
                }
                for chain_id, stats in chain_performance.items()
            ]
            
            top_chains.sort(key=lambda x: x["volume"], reverse=True)
            return top_chains[:limit]
            
        except Exception as e:
            print(f"Error getting top performing chains: {e}")
            return []
    
    async def _calculate_price_trends(self) -> Dict[str, List[float]]:
        """Calculate price trends for all chains"""
        try:
            trends = {}
            
            for chain_id, prices in self.price_history.items():
                if len(prices) >= 2:
                    # Calculate simple trend
                    recent_prices = list(prices)[-10:]  # Last 10 prices
                    if len(recent_prices) >= 2:
                        trend = (recent_prices[-1] - recent_prices[0]) / recent_prices[0] if recent_prices[0] != 0 else 0
                        trends[chain_id] = [float(trend)]
            
            return trends
            
        except Exception as e:
            print(f"Error calculating price trends: {e}")
            return {}
    
    async def _get_chain_types_distribution(self) -> Dict[str, int]:
        """Get distribution of chain types"""
        try:
            distribution = defaultdict(int)
            
            for listing in self.listings.values():
                distribution[listing.chain_type.value] += 1
            
            return dict(distribution)
            
        except Exception as e:
            print(f"Error getting chain types distribution: {e}")
            return {}
    
    async def _get_user_activity_metrics(self) -> Dict[str, Any]:
        """Get user activity metrics"""
        try:
            active_buyers = set()
            active_sellers = set()
            
            for transaction in self.transactions.values():
                if transaction.created_at >= datetime.now() - timedelta(days=7):
                    active_buyers.add(transaction.buyer_id)
                    active_sellers.add(transaction.seller_id)
            
            return {
                "active_buyers_7d": len(active_buyers),
                "active_sellers_7d": len(active_sellers),
                "total_unique_users": len(set(self.user_reputations.keys())),
                "average_reputation": sum(self.user_reputations.values()) / len(self.user_reputations) if self.user_reputations else 0
            }
            
        except Exception as e:
            print(f"Error getting user activity metrics: {e}")
            return {}
    
    async def _get_escrow_summary(self) -> Dict[str, Any]:
        """Get escrow contract summary"""
        try:
            active_escrows = len([e for e in self.escrow_contracts.values() if e["status"] == "active"])
            released_escrows = len([e for e in self.escrow_contracts.values() if e["status"] == "released"])
            
            total_escrow_value = sum(
                Decimal(str(e["amount"])) for e in self.escrow_contracts.values()
                if e["status"] == "active"
            )
            
            return {
                "active_escrows": active_escrows,
                "released_escrows": released_escrows,
                "total_escrow_value": float(total_escrow_value),
                "escrow_fee_collected": float(total_escrow_value * Decimal(str(self.thresholds['escrow_fee_percentage'])))
            }
            
        except Exception as e:
            print(f"Error getting escrow summary: {e}")
            return {}
