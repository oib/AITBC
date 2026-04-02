"""
Peer Health Monitoring Service
Monitors peer liveness and performance metrics
"""

import asyncio
import time
import ping3
import statistics
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .discovery import PeerNode, NodeStatus

class HealthMetric(Enum):
    LATENCY = "latency"
    AVAILABILITY = "availability"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"

@dataclass
class HealthStatus:
    node_id: str
    status: NodeStatus
    last_check: float
    latency_ms: float
    availability_percent: float
    throughput_mbps: float
    error_rate_percent: float
    consecutive_failures: int
    health_score: float

class PeerHealthMonitor:
    """Monitors health and performance of peer nodes"""
    
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self.health_status: Dict[str, HealthStatus] = {}
        self.running = False
        self.latency_history: Dict[str, List[float]] = {}
        self.max_history_size = 100
        
        # Health thresholds
        self.max_latency_ms = 1000
        self.min_availability_percent = 90.0
        self.min_health_score = 0.5
        self.max_consecutive_failures = 3
    
    async def start_monitoring(self, peers: Dict[str, PeerNode]):
        """Start health monitoring for peers"""
        self.running = True
        log_info("Starting peer health monitoring")
        
        while self.running:
            try:
                await self._check_all_peers(peers)
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                log_error(f"Health monitoring error: {e}")
                await asyncio.sleep(10)
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self.running = False
        log_info("Stopping peer health monitoring")
    
    async def _check_all_peers(self, peers: Dict[str, PeerNode]):
        """Check health of all peers"""
        tasks = []
        
        for node_id, peer in peers.items():
            if peer.status == NodeStatus.ONLINE:
                task = asyncio.create_task(self._check_peer_health(peer))
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_peer_health(self, peer: PeerNode):
        """Check health of individual peer"""
        start_time = time.time()
        
        try:
            # Check latency
            latency = await self._measure_latency(peer.address, peer.port)
            
            # Check availability
            availability = await self._check_availability(peer)
            
            # Check throughput
            throughput = await self._measure_throughput(peer)
            
            # Calculate health score
            health_score = self._calculate_health_score(latency, availability, throughput)
            
            # Update health status
            self._update_health_status(peer, NodeStatus.ONLINE, latency, availability, throughput, 0.0, health_score)
            
            # Reset consecutive failures
            if peer.node_id in self.health_status:
                self.health_status[peer.node_id].consecutive_failures = 0
            
        except Exception as e:
            log_error(f"Health check failed for peer {peer.node_id}: {e}")
            
            # Handle failure
            consecutive_failures = self.health_status.get(peer.node_id, HealthStatus(peer.node_id, NodeStatus.OFFLINE, 0, 0, 0, 0, 0, 0, 0.0)).consecutive_failures + 1
            
            if consecutive_failures >= self.max_consecutive_failures:
                self._update_health_status(peer, NodeStatus.OFFLINE, 0, 0, 0, 100.0, 0.0)
            else:
                self._update_health_status(peer, NodeStatus.ERROR, 0, 0, 0, 0.0, consecutive_failures, 0.0)
    
    async def _measure_latency(self, address: str, port: int) -> float:
        """Measure network latency to peer"""
        try:
            # Use ping3 for basic latency measurement
            latency = ping3.ping(address, timeout=2)
            
            if latency is not None:
                latency_ms = latency * 1000
                
                # Update latency history
                node_id = f"{address}:{port}"
                if node_id not in self.latency_history:
                    self.latency_history[node_id] = []
                
                self.latency_history[node_id].append(latency_ms)
                
                # Limit history size
                if len(self.latency_history[node_id]) > self.max_history_size:
                    self.latency_history[node_id].pop(0)
                
                return latency_ms
            else:
                return float('inf')
                
        except Exception as e:
            log_debug(f"Latency measurement failed for {address}:{port}: {e}")
            return float('inf')
    
    async def _check_availability(self, peer: PeerNode) -> float:
        """Check peer availability by attempting connection"""
        try:
            start_time = time.time()
            
            # Try to connect to peer
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(peer.address, peer.port),
                timeout=5.0
            )
            
            connection_time = (time.time() - start_time) * 1000
            
            writer.close()
            await writer.wait_closed()
            
            # Calculate availability based on recent history
            node_id = peer.node_id
            if node_id in self.health_status:
                # Simple availability calculation based on success rate
                recent_status = self.health_status[node_id]
                if recent_status.status == NodeStatus.ONLINE:
                    return min(100.0, recent_status.availability_percent + 5.0)
                else:
                    return max(0.0, recent_status.availability_percent - 10.0)
            else:
                return 100.0  # First successful connection
                
        except Exception as e:
            log_debug(f"Availability check failed for {peer.node_id}: {e}")
            return 0.0
    
    async def _measure_throughput(self, peer: PeerNode) -> float:
        """Measure network throughput to peer"""
        try:
            # Simple throughput test using small data transfer
            test_data = b"x" * 1024  # 1KB test data
            
            start_time = time.time()
            
            reader, writer = await asyncio.open_connection(peer.address, peer.port)
            
            # Send test data
            writer.write(test_data)
            await writer.drain()
            
            # Wait for echo response (if peer supports it)
            response = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            
            transfer_time = time.time() - start_time
            
            writer.close()
            await writer.wait_closed()
            
            # Calculate throughput in Mbps
            bytes_transferred = len(test_data) + len(response)
            throughput_mbps = (bytes_transferred * 8) / (transfer_time * 1024 * 1024)
            
            return throughput_mbps
            
        except Exception as e:
            log_debug(f"Throughput measurement failed for {peer.node_id}: {e}")
            return 0.0
    
    def _calculate_health_score(self, latency: float, availability: float, throughput: float) -> float:
        """Calculate overall health score"""
        # Latency score (lower is better)
        latency_score = max(0.0, 1.0 - (latency / self.max_latency_ms))
        
        # Availability score
        availability_score = availability / 100.0
        
        # Throughput score (higher is better, normalized to 10 Mbps)
        throughput_score = min(1.0, throughput / 10.0)
        
        # Weighted average
        health_score = (
            latency_score * 0.3 +
            availability_score * 0.4 +
            throughput_score * 0.3
        )
        
        return health_score
    
    def _update_health_status(self, peer: PeerNode, status: NodeStatus, latency: float, 
                            availability: float, throughput: float, error_rate: float,
                            consecutive_failures: int = 0, health_score: float = 0.0):
        """Update health status for peer"""
        self.health_status[peer.node_id] = HealthStatus(
            node_id=peer.node_id,
            status=status,
            last_check=time.time(),
            latency_ms=latency,
            availability_percent=availability,
            throughput_mbps=throughput,
            error_rate_percent=error_rate,
            consecutive_failures=consecutive_failures,
            health_score=health_score
        )
        
        # Update peer status in discovery
        peer.status = status
        peer.last_seen = time.time()
    
    def get_health_status(self, node_id: str) -> Optional[HealthStatus]:
        """Get health status for specific peer"""
        return self.health_status.get(node_id)
    
    def get_all_health_status(self) -> Dict[str, HealthStatus]:
        """Get health status for all peers"""
        return self.health_status.copy()
    
    def get_average_latency(self, node_id: str) -> Optional[float]:
        """Get average latency for peer"""
        node_key = f"{self.health_status.get(node_id, HealthStatus('', NodeStatus.OFFLINE, 0, 0, 0, 0, 0, 0, 0.0)).node_id}"
        
        if node_key in self.latency_history and self.latency_history[node_key]:
            return statistics.mean(self.latency_history[node_key])
        
        return None
    
    def get_healthy_peers(self) -> List[str]:
        """Get list of healthy peers"""
        return [
            node_id for node_id, status in self.health_status.items()
            if status.health_score >= self.min_health_score
        ]
    
    def get_unhealthy_peers(self) -> List[str]:
        """Get list of unhealthy peers"""
        return [
            node_id for node_id, status in self.health_status.items()
            if status.health_score < self.min_health_score
        ]

# Global health monitor
health_monitor: Optional[PeerHealthMonitor] = None

def get_health_monitor() -> Optional[PeerHealthMonitor]:
    """Get global health monitor"""
    return health_monitor

def create_health_monitor(check_interval: int = 60) -> PeerHealthMonitor:
    """Create and set global health monitor"""
    global health_monitor
    health_monitor = PeerHealthMonitor(check_interval)
    return health_monitor
