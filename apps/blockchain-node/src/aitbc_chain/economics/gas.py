"""
Gas Fee Model Implementation
Handles transaction fee calculation and gas optimization
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

class GasType(Enum):
    TRANSFER = "transfer"
    SMART_CONTRACT = "smart_contract"
    VALIDATOR_STAKE = "validator_stake"
    AGENT_OPERATION = "agent_operation"
    CONSENSUS = "consensus"
    MESSAGE = "message"
    RECEIPT_CLAIM = "receipt_claim"
    GPU_MARKETPLACE = "gpu_marketplace"
    EXCHANGE = "exchange"

@dataclass
class GasSchedule:
    gas_type: GasType
    base_gas: int
    gas_per_byte: int
    complexity_multiplier: float

@dataclass
class GasPrice:
    price_per_gas: Decimal
    timestamp: float
    block_height: int
    congestion_level: float

@dataclass
class TransactionGas:
    gas_used: int
    gas_limit: int
    gas_price: Decimal
    total_fee: Decimal
    refund: Decimal

class GasManager:
    """Manages gas fees and pricing"""
    
    def __init__(self, base_gas_price: float = 0.001):
        self.base_gas_price = Decimal(str(base_gas_price))
        self.current_gas_price = self.base_gas_price
        self.gas_schedules: Dict[GasType, GasSchedule] = {}
        self.price_history: List[GasPrice] = []
        self.congestion_history: List[float] = []
        
        # Gas parameters
        self.max_gas_price = self.base_gas_price * Decimal('100')  # 100x base price
        self.min_gas_price = self.base_gas_price * Decimal('0.1')   # 10% of base price
        self.congestion_threshold = 0.8  # 80% block utilization triggers price increase
        self.price_adjustment_factor = 1.1  # 10% price adjustment
        
        # Initialize gas schedules
        self._initialize_gas_schedules()
    
    def _initialize_gas_schedules(self):
        """Initialize gas schedules for different transaction types"""
        self.gas_schedules = {
            GasType.TRANSFER: GasSchedule(
                gas_type=GasType.TRANSFER,
                base_gas=21000,
                gas_per_byte=0,
                complexity_multiplier=1.0
            ),
            GasType.SMART_CONTRACT: GasSchedule(
                gas_type=GasType.SMART_CONTRACT,
                base_gas=21000,
                gas_per_byte=16,
                complexity_multiplier=1.5
            ),
            GasType.VALIDATOR_STAKE: GasSchedule(
                gas_type=GasType.VALIDATOR_STAKE,
                base_gas=50000,
                gas_per_byte=0,
                complexity_multiplier=1.2
            ),
            GasType.AGENT_OPERATION: GasSchedule(
                gas_type=GasType.AGENT_OPERATION,
                base_gas=100000,
                gas_per_byte=32,
                complexity_multiplier=2.0
            ),
            GasType.CONSENSUS: GasSchedule(
                gas_type=GasType.CONSENSUS,
                base_gas=80000,
                gas_per_byte=0,
                complexity_multiplier=1.0
            ),
            GasType.MESSAGE: GasSchedule(
                gas_type=GasType.MESSAGE,
                base_gas=21000,
                gas_per_byte=0,
                complexity_multiplier=1.0
            )
        }
    
    def estimate_gas(self, gas_type: GasType, data_size: int = 0, 
                    complexity_score: float = 1.0) -> int:
        """Estimate gas required for transaction"""
        schedule = self.gas_schedules.get(gas_type)
        if not schedule:
            raise ValueError(f"Unknown gas type: {gas_type}")
        
        # Calculate base gas
        gas = schedule.base_gas
        
        # Add data gas
        if schedule.gas_per_byte > 0:
            gas += data_size * schedule.gas_per_byte
        
        # Apply complexity multiplier
        gas = int(gas * schedule.complexity_multiplier * complexity_score)
        
        return gas
    
    def calculate_transaction_fee(self, gas_type: GasType, data_size: int = 0,
                                complexity_score: float = 1.0, 
                                gas_price: Optional[Decimal] = None) -> TransactionGas:
        """Calculate transaction fee"""
        # Estimate gas
        gas_limit = self.estimate_gas(gas_type, data_size, complexity_score)
        
        # Use provided gas price or current price
        price = gas_price or self.current_gas_price
        
        # Calculate total fee
        total_fee = Decimal(gas_limit) * price
        
        return TransactionGas(
            gas_used=gas_limit,  # Assume full gas used for estimation
            gas_limit=gas_limit,
            gas_price=price,
            total_fee=total_fee,
            refund=Decimal('0')
        )
    
    def update_gas_price(self, block_utilization: float, transaction_pool_size: int,
                        block_height: int) -> GasPrice:
        """Update gas price based on network conditions"""
        # Calculate congestion level
        congestion_level = max(block_utilization, transaction_pool_size / 1000)  # Normalize pool size
        
        # Store congestion history
        self.congestion_history.append(congestion_level)
        if len(self.congestion_history) > 100:  # Keep last 100 values
            self.congestion_history.pop(0)
        
        # Calculate new gas price
        if congestion_level > self.congestion_threshold:
            # Increase price
            new_price = self.current_gas_price * Decimal(str(self.price_adjustment_factor))
        else:
            # Decrease price (gradually)
            avg_congestion = sum(self.congestion_history[-10:]) / min(10, len(self.congestion_history))
            if avg_congestion < self.congestion_threshold * 0.7:
                new_price = self.current_gas_price / Decimal(str(self.price_adjustment_factor))
            else:
                new_price = self.current_gas_price
        
        # Apply price bounds
        new_price = max(self.min_gas_price, min(self.max_gas_price, new_price))
        
        # Update current price
        self.current_gas_price = new_price
        
        # Record price history
        gas_price = GasPrice(
            price_per_gas=new_price,
            timestamp=time.time(),
            block_height=block_height,
            congestion_level=congestion_level
        )
        
        self.price_history.append(gas_price)
        if len(self.price_history) > 1000:  # Keep last 1000 values
            self.price_history.pop(0)
        
        return gas_price
    
    def get_optimal_gas_price(self, priority: str = "standard") -> Decimal:
        """Get optimal gas price based on priority"""
        if priority == "fast":
            # 2x current price for fast inclusion
            return min(self.current_gas_price * Decimal('2'), self.max_gas_price)
        elif priority == "slow":
            # 0.5x current price for slow inclusion
            return max(self.current_gas_price * Decimal('0.5'), self.min_gas_price)
        else:
            # Standard price
            return self.current_gas_price
    
    def predict_gas_price(self, blocks_ahead: int = 5) -> Decimal:
        """Predict gas price for future blocks"""
        if len(self.price_history) < 10:
            return self.current_gas_price
        
        # Simple linear prediction based on recent trend
        recent_prices = [p.price_per_gas for p in self.price_history[-10:]]
        
        # Calculate trend
        if len(recent_prices) >= 2:
            price_change = recent_prices[-1] - recent_prices[-2]
            predicted_price = self.current_gas_price + (price_change * blocks_ahead)
        else:
            predicted_price = self.current_gas_price
        
        # Apply bounds
        return max(self.min_gas_price, min(self.max_gas_price, predicted_price))
    
    def get_gas_statistics(self) -> Dict:
        """Get gas system statistics"""
        if not self.price_history:
            return {
                'current_price': float(self.current_gas_price),
                'price_history_length': 0,
                'average_price': float(self.current_gas_price),
                'price_volatility': 0.0
            }
        
        prices = [p.price_per_gas for p in self.price_history]
        avg_price = sum(prices) / len(prices)
        
        # Calculate volatility (standard deviation)
        if len(prices) > 1:
            variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
            volatility = (variance ** 0.5) / avg_price
        else:
            volatility = 0.0
        
        return {
            'current_price': float(self.current_gas_price),
            'price_history_length': len(self.price_history),
            'average_price': float(avg_price),
            'price_volatility': float(volatility),
            'min_price': float(min(prices)),
            'max_price': float(max(prices)),
            'congestion_history_length': len(self.congestion_history),
            'average_congestion': sum(self.congestion_history) / len(self.congestion_history) if self.congestion_history else 0.0
        }

class GasOptimizer:
    """Optimizes gas usage and fees"""
    
    def __init__(self, gas_manager: GasManager):
        self.gas_manager = gas_manager
        self.optimization_history: List[Dict] = []
    
    def optimize_transaction(self, gas_type: GasType, data: bytes, 
                          priority: str = "standard") -> Dict:
        """Optimize transaction for gas efficiency"""
        data_size = len(data)
        
        # Estimate base gas
        base_gas = self.gas_manager.estimate_gas(gas_type, data_size)
        
        # Calculate optimal gas price
        optimal_price = self.gas_manager.get_optimal_gas_price(priority)
        
        # Optimization suggestions
        optimizations = []
        
        # Data optimization
        if data_size > 1000 and gas_type == GasType.SMART_CONTRACT:
            optimizations.append({
                'type': 'data_compression',
                'potential_savings': data_size * 8,  # 8 gas per byte
                'description': 'Compress transaction data to reduce gas costs'
            })
        
        # Timing optimization
        if priority == "standard":
            fast_price = self.gas_manager.get_optimal_gas_price("fast")
            slow_price = self.gas_manager.get_optimal_gas_price("slow")
            
            if slow_price < optimal_price:
                savings = (optimal_price - slow_price) * base_gas
                optimizations.append({
                    'type': 'timing_optimization',
                    'potential_savings': float(savings),
                    'description': 'Use slower priority for lower fees'
                })
        
        # Bundle similar transactions
        if gas_type in [GasType.TRANSFER, GasType.VALIDATOR_STAKE]:
            optimizations.append({
                'type': 'transaction_bundling',
                'potential_savings': base_gas * 0.3,  # 30% savings estimate
                'description': 'Bundle similar transactions to share base gas costs'
            })
        
        # Record optimization
        optimization_result = {
            'gas_type': gas_type.value,
            'data_size': data_size,
            'base_gas': base_gas,
            'optimal_price': float(optimal_price),
            'estimated_fee': float(base_gas * optimal_price),
            'optimizations': optimizations,
            'timestamp': time.time()
        }
        
        self.optimization_history.append(optimization_result)
        
        return optimization_result
    
    def get_optimization_summary(self) -> Dict:
        """Get optimization summary statistics"""
        if not self.optimization_history:
            return {
                'total_optimizations': 0,
                'average_savings': 0.0,
                'most_common_type': None
            }
        
        total_savings = 0
        type_counts = {}
        
        for opt in self.optimization_history:
            for suggestion in opt['optimizations']:
                total_savings += suggestion['potential_savings']
                opt_type = suggestion['type']
                type_counts[opt_type] = type_counts.get(opt_type, 0) + 1
        
        most_common_type = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else None
        
        return {
            'total_optimizations': len(self.optimization_history),
            'total_potential_savings': total_savings,
            'average_savings': total_savings / len(self.optimization_history) if self.optimization_history else 0,
            'most_common_type': most_common_type,
            'optimization_types': list(type_counts.keys())
        }

# Global gas manager and optimizer
gas_manager: Optional[GasManager] = None
gas_optimizer: Optional[GasOptimizer] = None

def get_gas_manager() -> Optional[GasManager]:
    """Get global gas manager"""
    return gas_manager

def create_gas_manager(base_gas_price: float = 0.001) -> GasManager:
    """Create and set global gas manager"""
    global gas_manager
    gas_manager = GasManager(base_gas_price)
    return gas_manager

def get_gas_optimizer() -> Optional[GasOptimizer]:
    """Get global gas optimizer"""
    return gas_optimizer

def create_gas_optimizer(gas_manager: GasManager) -> GasOptimizer:
    """Create and set global gas optimizer"""
    global gas_optimizer
    gas_optimizer = GasOptimizer(gas_manager)
    return gas_optimizer
