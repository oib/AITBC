"""
Marketplace Real-time Performance Monitor
Implements comprehensive real-time monitoring and analytics for the AITBC marketplace.
"""

import time
import asyncio
import logging
from typing import Dict, List, Optional, Any, collections
from datetime import datetime, timedelta
import collections

logger = logging.getLogger(__name__)

class TimeSeriesData:
    """Efficient in-memory time series data structure for real-time metrics"""
    
    def __init__(self, max_points: int = 3600): # Default 1 hour of second-level data
        self.max_points = max_points
        self.timestamps = collections.deque(maxlen=max_points)
        self.values = collections.deque(maxlen=max_points)
        
    def add(self, value: float, timestamp: float = None):
        self.timestamps.append(timestamp or time.time())
        self.values.append(value)
        
    def get_latest(self) -> Optional[float]:
        return self.values[-1] if self.values else None
        
    def get_average(self, window_seconds: int = 60) -> float:
        if not self.values:
            return 0.0
            
        cutoff = time.time() - window_seconds
        valid_values = [v for t, v in zip(self.timestamps, self.values) if t >= cutoff]
        
        return sum(valid_values) / len(valid_values) if valid_values else 0.0
        
    def get_percentile(self, percentile: float, window_seconds: int = 60) -> float:
        if not self.values:
            return 0.0
            
        cutoff = time.time() - window_seconds
        valid_values = sorted([v for t, v in zip(self.timestamps, self.values) if t >= cutoff])
        
        if not valid_values:
            return 0.0
            
        idx = int(len(valid_values) * percentile)
        idx = min(max(idx, 0), len(valid_values) - 1)
        return valid_values[idx]

class MarketplaceMonitor:
    """Real-time performance monitoring system for the marketplace"""
    
    def __init__(self):
        # API Metrics
        self.api_latency_ms = TimeSeriesData()
        self.api_requests_per_sec = TimeSeriesData()
        self.api_error_rate = TimeSeriesData()
        
        # Trading Metrics
        self.order_matching_time_ms = TimeSeriesData()
        self.trades_per_sec = TimeSeriesData()
        self.active_orders = TimeSeriesData()
        
        # Resource Metrics
        self.gpu_utilization_pct = TimeSeriesData()
        self.network_bandwidth_mbps = TimeSeriesData()
        self.active_providers = TimeSeriesData()
        
        # internal tracking
        self._request_counter = 0
        self._error_counter = 0
        self._trade_counter = 0
        self._last_tick = time.time()
        
        self.is_running = False
        self._monitor_task = None
        
        # Alert thresholds
        self.alert_thresholds = {
            'api_latency_p95_ms': 500.0,
            'api_error_rate_pct': 5.0,
            'gpu_utilization_pct': 90.0,
            'matching_time_ms': 100.0
        }
        
        self.active_alerts = []
        
    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._monitor_task = asyncio.create_task(self._metric_tick_loop())
        logger.info("Marketplace Monitor started")
        
    async def stop(self):
        self.is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
        logger.info("Marketplace Monitor stopped")
        
    def record_api_call(self, latency_ms: float, is_error: bool = False):
        """Record an API request for monitoring"""
        self.api_latency_ms.add(latency_ms)
        self._request_counter += 1
        if is_error:
            self._error_counter += 1
            
    def record_trade(self, matching_time_ms: float):
        """Record a successful trade match"""
        self.order_matching_time_ms.add(matching_time_ms)
        self._trade_counter += 1
        
    def update_resource_metrics(self, gpu_util: float, bandwidth: float, providers: int, orders: int):
        """Update system resource metrics"""
        self.gpu_utilization_pct.add(gpu_util)
        self.network_bandwidth_mbps.add(bandwidth)
        self.active_providers.add(providers)
        self.active_orders.add(orders)
        
    async def _metric_tick_loop(self):
        """Background task that aggregates metrics every second"""
        while self.is_running:
            try:
                now = time.time()
                elapsed = now - self._last_tick
                
                if elapsed >= 1.0:
                    # Calculate rates
                    req_per_sec = self._request_counter / elapsed
                    trades_per_sec = self._trade_counter / elapsed
                    error_rate = (self._error_counter / max(1, self._request_counter)) * 100
                    
                    # Store metrics
                    self.api_requests_per_sec.add(req_per_sec)
                    self.trades_per_sec.add(trades_per_sec)
                    self.api_error_rate.add(error_rate)
                    
                    # Reset counters
                    self._request_counter = 0
                    self._error_counter = 0
                    self._trade_counter = 0
                    self._last_tick = now
                    
                    # Evaluate alerts
                    self._evaluate_alerts()
                    
                await asyncio.sleep(1.0 - (time.time() - now)) # Sleep for remainder of second
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitor tick loop: {e}")
                await asyncio.sleep(1.0)
                
    def _evaluate_alerts(self):
        """Check metrics against thresholds and generate alerts"""
        current_alerts = []
        
        # API Latency Alert
        p95_latency = self.api_latency_ms.get_percentile(0.95, window_seconds=60)
        if p95_latency > self.alert_thresholds['api_latency_p95_ms']:
            current_alerts.append({
                'id': f"alert_latency_{int(time.time())}",
                'severity': 'high' if p95_latency > self.alert_thresholds['api_latency_p95_ms'] * 2 else 'medium',
                'metric': 'api_latency',
                'value': p95_latency,
                'threshold': self.alert_thresholds['api_latency_p95_ms'],
                'message': f"High API Latency (p95): {p95_latency:.2f}ms",
                'timestamp': datetime.utcnow().isoformat()
            })
            
        # Error Rate Alert
        avg_error_rate = self.api_error_rate.get_average(window_seconds=60)
        if avg_error_rate > self.alert_thresholds['api_error_rate_pct']:
            current_alerts.append({
                'id': f"alert_error_{int(time.time())}",
                'severity': 'critical',
                'metric': 'error_rate',
                'value': avg_error_rate,
                'threshold': self.alert_thresholds['api_error_rate_pct'],
                'message': f"High API Error Rate: {avg_error_rate:.2f}%",
                'timestamp': datetime.utcnow().isoformat()
            })
            
        # Matching Time Alert
        avg_matching = self.order_matching_time_ms.get_average(window_seconds=60)
        if avg_matching > self.alert_thresholds['matching_time_ms']:
            current_alerts.append({
                'id': f"alert_matching_{int(time.time())}",
                'severity': 'medium',
                'metric': 'matching_time',
                'value': avg_matching,
                'threshold': self.alert_thresholds['matching_time_ms'],
                'message': f"Slow Order Matching: {avg_matching:.2f}ms",
                'timestamp': datetime.utcnow().isoformat()
            })
            
        self.active_alerts = current_alerts
        
        if current_alerts:
            # In a real system, this would trigger webhooks, Slack/Discord messages, etc.
            for alert in current_alerts:
                if alert['severity'] in ['high', 'critical']:
                    logger.warning(f"MARKETPLACE ALERT: {alert['message']}")

    def get_realtime_dashboard_data(self) -> Dict[str, Any]:
        """Get aggregated data formatted for the frontend dashboard"""
        return {
            'status': 'degraded' if any(a['severity'] in ['high', 'critical'] for a in self.active_alerts) else 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'current_metrics': {
                'api': {
                    'rps': round(self.api_requests_per_sec.get_latest() or 0, 2),
                    'latency_p50_ms': round(self.api_latency_ms.get_percentile(0.50, 60), 2),
                    'latency_p95_ms': round(self.api_latency_ms.get_percentile(0.95, 60), 2),
                    'error_rate_pct': round(self.api_error_rate.get_average(60), 2)
                },
                'trading': {
                    'tps': round(self.trades_per_sec.get_latest() or 0, 2),
                    'matching_time_ms': round(self.order_matching_time_ms.get_average(60), 2),
                    'active_orders': int(self.active_orders.get_latest() or 0)
                },
                'network': {
                    'active_providers': int(self.active_providers.get_latest() or 0),
                    'gpu_utilization_pct': round(self.gpu_utilization_pct.get_latest() or 0, 2),
                    'bandwidth_mbps': round(self.network_bandwidth_mbps.get_latest() or 0, 2)
                }
            },
            'alerts': self.active_alerts
        }

# Global instance
monitor = MarketplaceMonitor()
