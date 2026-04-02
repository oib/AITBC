"""
Gas Optimization System
Optimizes gas usage and fee efficiency for smart contracts
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

class OptimizationStrategy(Enum):
    BATCH_OPERATIONS = "batch_operations"
    LAZY_EVALUATION = "lazy_evaluation"
    STATE_COMPRESSION = "state_compression"
    EVENT_FILTERING = "event_filtering"
    STORAGE_OPTIMIZATION = "storage_optimization"

@dataclass
class GasMetric:
    contract_address: str
    function_name: str
    gas_used: int
    gas_limit: int
    execution_time: float
    timestamp: float
    optimization_applied: Optional[str]

@dataclass
class OptimizationResult:
    strategy: OptimizationStrategy
    original_gas: int
    optimized_gas: int
    gas_savings: int
    savings_percentage: float
    implementation_cost: Decimal
    net_benefit: Decimal

class GasOptimizer:
    """Optimizes gas usage for smart contracts"""
    
    def __init__(self):
        self.gas_metrics: List[GasMetric] = []
        self.optimization_results: List[OptimizationResult] = []
        self.optimization_strategies = self._initialize_strategies()
        
        # Optimization parameters
        self.min_optimization_threshold = 1000  # Minimum gas to consider optimization
        self.optimization_target_savings = 0.1  # 10% minimum savings
        self.max_optimization_cost = Decimal('0.01')  # Maximum cost per optimization
        self.metric_retention_period = 86400 * 7  # 7 days
        
        # Gas price tracking
        self.gas_price_history: List[Dict] = []
        self.current_gas_price = Decimal('0.001')
    
    def _initialize_strategies(self) -> Dict[OptimizationStrategy, Dict]:
        """Initialize optimization strategies"""
        return {
            OptimizationStrategy.BATCH_OPERATIONS: {
                'description': 'Batch multiple operations into single transaction',
                'potential_savings': 0.3,  # 30% potential savings
                'implementation_cost': Decimal('0.005'),
                'applicable_functions': ['transfer', 'approve', 'mint']
            },
            OptimizationStrategy.LAZY_EVALUATION: {
                'description': 'Defer expensive computations until needed',
                'potential_savings': 0.2,  # 20% potential savings
                'implementation_cost': Decimal('0.003'),
                'applicable_functions': ['calculate', 'validate', 'process']
            },
            OptimizationStrategy.STATE_COMPRESSION: {
                'description': 'Compress state data to reduce storage costs',
                'potential_savings': 0.4,  # 40% potential savings
                'implementation_cost': Decimal('0.008'),
                'applicable_functions': ['store', 'update', 'save']
            },
            OptimizationStrategy.EVENT_FILTERING: {
                'description': 'Filter events to reduce emission costs',
                'potential_savings': 0.15,  # 15% potential savings
                'implementation_cost': Decimal('0.002'),
                'applicable_functions': ['emit', 'log', 'notify']
            },
            OptimizationStrategy.STORAGE_OPTIMIZATION: {
                'description': 'Optimize storage patterns and data structures',
                'potential_savings': 0.25,  # 25% potential savings
                'implementation_cost': Decimal('0.006'),
                'applicable_functions': ['set', 'add', 'remove']
            }
        }
    
    async def record_gas_usage(self, contract_address: str, function_name: str,
                              gas_used: int, gas_limit: int, execution_time: float,
                              optimization_applied: Optional[str] = None):
        """Record gas usage metrics"""
        metric = GasMetric(
            contract_address=contract_address,
            function_name=function_name,
            gas_used=gas_used,
            gas_limit=gas_limit,
            execution_time=execution_time,
            timestamp=time.time(),
            optimization_applied=optimization_applied
        )
        
        self.gas_metrics.append(metric)
        
        # Limit history size
        if len(self.gas_metrics) > 10000:
            self.gas_metrics = self.gas_metrics[-5000]
        
        # Trigger optimization analysis if threshold met
        if gas_used >= self.min_optimization_threshold:
            asyncio.create_task(self._analyze_optimization_opportunity(metric))
    
    async def _analyze_optimization_opportunity(self, metric: GasMetric):
        """Analyze if optimization is beneficial"""
        # Get historical average for this function
        historical_metrics = [
            m for m in self.gas_metrics
            if m.function_name == metric.function_name and
            m.contract_address == metric.contract_address and
            not m.optimization_applied
        ]
        
        if len(historical_metrics) < 5:  # Need sufficient history
            return
        
        avg_gas = sum(m.gas_used for m in historical_metrics) / len(historical_metrics)
        
        # Test each optimization strategy
        for strategy, config in self.optimization_strategies.items():
            if self._is_strategy_applicable(strategy, metric.function_name):
                potential_savings = avg_gas * config['potential_savings']
                
                if potential_savings >= self.min_optimization_threshold:
                    # Calculate net benefit
                    gas_price = self.current_gas_price
                    gas_savings_value = potential_savings * gas_price
                    net_benefit = gas_savings_value - config['implementation_cost']
                    
                    if net_benefit > 0:
                        # Create optimization result
                        result = OptimizationResult(
                            strategy=strategy,
                            original_gas=int(avg_gas),
                            optimized_gas=int(avg_gas - potential_savings),
                            gas_savings=int(potential_savings),
                            savings_percentage=config['potential_savings'],
                            implementation_cost=config['implementation_cost'],
                            net_benefit=net_benefit
                        )
                        
                        self.optimization_results.append(result)
                        
                        # Keep only recent results
                        if len(self.optimization_results) > 1000:
                            self.optimization_results = self.optimization_results[-500]
                        
                        log_info(f"Optimization opportunity found: {strategy.value} for {metric.function_name} - Potential savings: {potential_savings} gas")
    
    def _is_strategy_applicable(self, strategy: OptimizationStrategy, function_name: str) -> bool:
        """Check if optimization strategy is applicable to function"""
        config = self.optimization_strategies.get(strategy, {})
        applicable_functions = config.get('applicable_functions', [])
        
        # Check if function name contains any applicable keywords
        for applicable in applicable_functions:
            if applicable.lower() in function_name.lower():
                return True
        
        return False
    
    async def apply_optimization(self, contract_address: str, function_name: str,
                               strategy: OptimizationStrategy) -> Tuple[bool, str]:
        """Apply optimization strategy to contract function"""
        try:
            # Validate strategy
            if strategy not in self.optimization_strategies:
                return False, "Unknown optimization strategy"
            
            # Check applicability
            if not self._is_strategy_applicable(strategy, function_name):
                return False, "Strategy not applicable to this function"
            
            # Get optimization result
            result = None
            for res in self.optimization_results:
                if (res.strategy == strategy and 
                    res.strategy in self.optimization_strategies):
                    result = res
                    break
            
            if not result:
                return False, "No optimization analysis available"
            
            # Check if net benefit is positive
            if result.net_benefit <= 0:
                return False, "Optimization not cost-effective"
            
            # Apply optimization (in real implementation, this would modify contract code)
            success = await self._implement_optimization(contract_address, function_name, strategy)
            
            if success:
                # Record optimization
                await self.record_gas_usage(
                    contract_address, function_name, result.optimized_gas,
                    result.optimized_gas, 0.0, strategy.value
                )
                
                log_info(f"Optimization applied: {strategy.value} to {function_name}")
                return True, f"Optimization applied successfully. Gas savings: {result.gas_savings}"
            else:
                return False, "Optimization implementation failed"
                
        except Exception as e:
            return False, f"Optimization error: {str(e)}"
    
    async def _implement_optimization(self, contract_address: str, function_name: str,
                                    strategy: OptimizationStrategy) -> bool:
        """Implement the optimization strategy"""
        try:
            # In real implementation, this would:
            # 1. Analyze contract bytecode
            # 2. Apply optimization patterns
            # 3. Generate optimized bytecode
            # 4. Deploy optimized version
            # 5. Verify functionality
            
            # Simulate implementation
            await asyncio.sleep(2)  # Simulate optimization time
            
            return True
            
        except Exception as e:
            log_error(f"Optimization implementation error: {e}")
            return False
    
    async def update_gas_price(self, new_price: Decimal):
        """Update current gas price"""
        self.current_gas_price = new_price
        
        # Record price history
        self.gas_price_history.append({
            'price': float(new_price),
            'timestamp': time.time()
        })
        
        # Limit history size
        if len(self.gas_price_history) > 1000:
            self.gas_price_history = self.gas_price_history[-500]
        
        # Re-evaluate optimization opportunities with new price
        asyncio.create_task(self._reevaluate_optimizations())
    
    async def _reevaluate_optimizations(self):
        """Re-evaluate optimization opportunities with new gas price"""
        # Clear old results and re-analyze
        self.optimization_results.clear()
        
        # Re-analyze recent metrics
        recent_metrics = [
            m for m in self.gas_metrics
            if time.time() - m.timestamp < 3600  # Last hour
        ]
        
        for metric in recent_metrics:
            if metric.gas_used >= self.min_optimization_threshold:
                await self._analyze_optimization_opportunity(metric)
    
    async def get_optimization_recommendations(self, contract_address: Optional[str] = None,
                                             limit: int = 10) -> List[Dict]:
        """Get optimization recommendations"""
        recommendations = []
        
        for result in self.optimization_results:
            if contract_address and result.strategy.value not in self.optimization_strategies:
                continue
            
            if result.net_benefit > 0:
                recommendations.append({
                    'strategy': result.strategy.value,
                    'function': 'contract_function',  # Would map to actual function
                    'original_gas': result.original_gas,
                    'optimized_gas': result.optimized_gas,
                    'gas_savings': result.gas_savings,
                    'savings_percentage': result.savings_percentage,
                    'net_benefit': float(result.net_benefit),
                    'implementation_cost': float(result.implementation_cost)
                })
        
        # Sort by net benefit
        recommendations.sort(key=lambda x: x['net_benefit'], reverse=True)
        
        return recommendations[:limit]
    
    async def get_gas_statistics(self) -> Dict:
        """Get gas usage statistics"""
        if not self.gas_metrics:
            return {
                'total_transactions': 0,
                'average_gas_used': 0,
                'total_gas_used': 0,
                'gas_efficiency': 0,
                'optimization_opportunities': 0
            }
        
        total_transactions = len(self.gas_metrics)
        total_gas_used = sum(m.gas_used for m in self.gas_metrics)
        average_gas_used = total_gas_used / total_transactions
        
        # Calculate efficiency (gas used vs gas limit)
        efficiency_scores = [
            m.gas_used / m.gas_limit for m in self.gas_metrics
            if m.gas_limit > 0
        ]
        avg_efficiency = sum(efficiency_scores) / len(efficiency_scores) if efficiency_scores else 0
        
        # Optimization opportunities
        optimization_count = len([
            result for result in self.optimization_results
            if result.net_benefit > 0
        ])
        
        return {
            'total_transactions': total_transactions,
            'average_gas_used': average_gas_used,
            'total_gas_used': total_gas_used,
            'gas_efficiency': avg_efficiency,
            'optimization_opportunities': optimization_count,
            'current_gas_price': float(self.current_gas_price),
            'total_optimizations_applied': len([
                m for m in self.gas_metrics
                if m.optimization_applied
            ])
        }

# Global gas optimizer
gas_optimizer: Optional[GasOptimizer] = None

def get_gas_optimizer() -> Optional[GasOptimizer]:
    """Get global gas optimizer"""
    return gas_optimizer

def create_gas_optimizer() -> GasOptimizer:
    """Create and set global gas optimizer"""
    global gas_optimizer
    gas_optimizer = GasOptimizer()
    return gas_optimizer
