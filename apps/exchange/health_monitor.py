#!/usr/bin/env python3
"""
Exchange Health Monitoring and Failover System
Monitors exchange health and provides automatic failover capabilities
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from aitbc import get_logger
from real_exchange_integration import exchange_manager, ExchangeStatus, ExchangeHealth

logger = get_logger(__name__)

class FailoverStrategy(str, Enum):
    """Failover strategies"""
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    PRIORITY_BASED = "priority_based"

@dataclass
class FailoverConfig:
    """Failover configuration"""
    strategy: FailoverStrategy
    health_check_interval: int = 30  # seconds
    max_failures: int = 3
    recovery_check_interval: int = 60  # seconds
    priority_order: List[str] = None  # Exchange priority for failover

class ExchangeHealthMonitor:
    """Monitors exchange health and manages failover"""
    
    def __init__(self, config: FailoverConfig):
        self.config = config
        self.health_history: Dict[str, List[ExchangeHealth]] = {}
        self.failure_counts: Dict[str, int] = {}
        self.active_exchanges: List[str] = []
        self.monitoring_task = None
        self.is_monitoring = False
        
    async def start_monitoring(self):
        """Start health monitoring"""
        if self.is_monitoring:
            logger.warning("⚠️  Health monitoring already running")
            return
        
        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info("🔍 Exchange health monitoring started")
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("🔍 Exchange health monitoring stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                await self._check_all_exchanges()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def _check_all_exchanges(self):
        """Check health of all connected exchanges"""
        try:
            health_status = await exchange_manager.get_all_health_status()
            
            for exchange_name, health in health_status.items():
                await self._process_health_check(exchange_name, health)
                
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
    
    async def _process_health_check(self, exchange_name: str, health: ExchangeHealth):
        """Process individual exchange health check"""
        # Store health history
        if exchange_name not in self.health_history:
            self.health_history[exchange_name] = []
        
        self.health_history[exchange_name].append(health)
        
        # Keep only last 100 checks
        if len(self.health_history[exchange_name]) > 100:
            self.health_history[exchange_name] = self.health_history[exchange_name][-100:]
        
        # Check for failures
        if health.status == ExchangeStatus.ERROR:
            self.failure_counts[exchange_name] = self.failure_counts.get(exchange_name, 0) + 1
            
            logger.warning(f"⚠️  {exchange_name} failure #{self.failure_counts[exchange_name]}: {health.error_message}")
            
            # Trigger failover if needed
            if self.failure_counts[exchange_name] >= self.config.max_failures:
                await self._trigger_failover(exchange_name)
        else:
            # Reset failure count on successful check
            if exchange_name in self.failure_counts and self.failure_counts[exchange_name] > 0:
                logger.info(f"✅ {exchange_name} recovered after {self.failure_counts[exchange_name]} failures")
                self.failure_counts[exchange_name] = 0
            
            # Update active exchanges list
            if exchange_name not in self.active_exchanges:
                self.active_exchanges.append(exchange_name)
    
    async def _trigger_failover(self, failed_exchange: str):
        """Trigger failover for failed exchange"""
        logger.error(f"🚨 FAILOVER TRIGGERED: {failed_exchange} failed {self.failure_counts[failed_exchange]} times")
        
        if self.config.strategy == FailoverStrategy.AUTOMATIC:
            await self._automatic_failover(failed_exchange)
        elif self.config.strategy == FailoverStrategy.PRIORITY_BASED:
            await self._priority_based_failover(failed_exchange)
        else:
            logger.info(f"📝 Manual failover required for {failed_exchange}")
    
    async def _automatic_failover(self, failed_exchange: str):
        """Automatic failover to any healthy exchange"""
        healthy_exchanges = [
            ex for ex in exchange_manager.exchanges.keys()
            if ex != failed_exchange and self.failure_counts.get(ex, 0) < self.config.max_failures
        ]
        
        if healthy_exchanges:
            backup = healthy_exchanges[0]
            logger.info(f"🔄 Automatic failover: {failed_exchange} → {backup}")
            await self._redirect_orders(failed_exchange, backup)
        else:
            logger.error(f"❌ No healthy exchanges available for failover")
    
    async def _priority_based_failover(self, failed_exchange: str):
        """Priority-based failover"""
        if not self.config.priority_order:
            logger.warning("⚠️  No priority order configured, falling back to automatic")
            await self._automatic_failover(failed_exchange)
            return
        
        # Find next healthy exchange in priority order
        for exchange in self.config.priority_order:
            if (exchange != failed_exchange and 
                exchange in exchange_manager.exchanges and
                self.failure_counts.get(exchange, 0) < self.config.max_failures):
                
                logger.info(f"🔄 Priority-based failover: {failed_exchange} → {exchange}")
                await self._redirect_orders(failed_exchange, exchange)
                return
        
        logger.error(f"❌ No healthy exchanges available in priority order")
    
    async def _redirect_orders(self, from_exchange: str, to_exchange: str):
        """Redirect orders from failed exchange to backup"""
        # This would integrate with the order management system
        logger.info(f"📦 Redirecting orders from {from_exchange} to {to_exchange}")
        # Implementation would depend on order tracking system
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary"""
        summary = {
            "monitoring_active": self.is_monitoring,
            "active_exchanges": self.active_exchanges.copy(),
            "failure_counts": self.failure_counts.copy(),
            "exchange_health": {},
            "uptime_stats": {}
        }
        
        # Calculate uptime statistics
        for exchange_name, history in self.health_history.items():
            if history:
                total_checks = len(history)
                successful_checks = sum(1 for h in history if h.status == ExchangeStatus.CONNECTED)
                uptime_pct = (successful_checks / total_checks) * 100 if total_checks > 0 else 0
                
                avg_latency = sum(h.latency_ms for h in history if h.status == ExchangeStatus.CONNECTED) / successful_checks if successful_checks > 0 else 0
                
                summary["exchange_health"][exchange_name] = {
                    "status": history[-1].status.value if history else "unknown",
                    "last_check": history[-1].last_check.strftime('%H:%M:%S') if history else None,
                    "avg_latency_ms": round(avg_latency, 2),
                    "total_checks": total_checks,
                    "successful_checks": successful_checks,
                    "uptime_percentage": round(uptime_pct, 2)
                }
        
        return summary
    
    def get_alerts(self) -> List[Dict[str, Any]]:
        """Get current alerts"""
        alerts = []
        
        for exchange_name, count in self.failure_counts.items():
            if count >= self.config.max_failures:
                alerts.append({
                    "level": "critical",
                    "exchange": exchange_name,
                    "message": f"Exchange has failed {count} times",
                    "timestamp": datetime.now()
                })
            elif count > 0:
                alerts.append({
                    "level": "warning",
                    "exchange": exchange_name,
                    "message": f"Exchange has {count} recent failures",
                    "timestamp": datetime.now()
                })
        
        return alerts

# Global instance
default_config = FailoverConfig(
    strategy=FailoverStrategy.AUTOMATIC,
    health_check_interval=30,
    max_failures=3,
    priority_order=["binance", "coinbasepro", "kraken"]
)

health_monitor = ExchangeHealthMonitor(default_config)

# CLI Functions
async def start_health_monitoring():
    """Start health monitoring"""
    await health_monitor.start_monitoring()

async def stop_health_monitoring():
    """Stop health monitoring"""
    await health_monitor.stop_monitoring()

def get_health_summary():
    """Get health summary"""
    return health_monitor.get_health_summary()

def get_alerts():
    """Get current alerts"""
    return health_monitor.get_alerts()

# Test function
async def test_health_monitoring():
    """Test health monitoring system"""
    print("🧪 Testing Health Monitoring System...")
    
    # Start monitoring
    await start_health_monitoring()
    print("✅ Health monitoring started")
    
    # Run for a few seconds to see it work
    await asyncio.sleep(5)
    
    # Get summary
    summary = get_health_summary()
    print(f"📊 Health Summary: {summary}")
    
    # Get alerts
    alerts = get_alerts()
    print(f"🚨 Alerts: {len(alerts)}")
    
    # Stop monitoring
    await stop_health_monitoring()
    print("🔍 Health monitoring stopped")

if __name__ == "__main__":
    asyncio.run(test_health_monitoring())