"""
Network Topology Optimization
Optimizes peer connection strategies for network performance
"""

import asyncio
import networkx as nx
import time
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from .discovery import PeerNode, P2PDiscovery
from .health import PeerHealthMonitor, HealthStatus

class TopologyStrategy(Enum):
    SMALL_WORLD = "small_world"
    SCALE_FREE = "scale_free"
    MESH = "mesh"
    HYBRID = "hybrid"

@dataclass
class ConnectionWeight:
    source: str
    target: str
    weight: float
    latency: float
    bandwidth: float
    reliability: float

class NetworkTopology:
    """Manages and optimizes network topology"""
    
    def __init__(self, discovery: P2PDiscovery, health_monitor: PeerHealthMonitor):
        self.discovery = discovery
        self.health_monitor = health_monitor
        self.graph = nx.Graph()
        self.strategy = TopologyStrategy.HYBRID
        self.optimization_interval = 300  # 5 minutes
        self.max_degree = 8
        self.min_degree = 3
        self.running = False
        
        # Topology metrics
        self.avg_path_length = 0
        self.clustering_coefficient = 0
        self.network_efficiency = 0
    
    async def start_optimization(self):
        """Start topology optimization service"""
        self.running = True
        log_info("Starting network topology optimization")
        
        # Initialize graph
        await self._build_initial_graph()
        
        while self.running:
            try:
                await self._optimize_topology()
                await self._calculate_metrics()
                await asyncio.sleep(self.optimization_interval)
            except Exception as e:
                log_error(f"Topology optimization error: {e}")
                await asyncio.sleep(30)
    
    async def stop_optimization(self):
        """Stop topology optimization service"""
        self.running = False
        log_info("Stopping network topology optimization")
    
    async def _build_initial_graph(self):
        """Build initial network graph from current peers"""
        self.graph.clear()
        
        # Add all peers as nodes
        for peer in self.discovery.get_peer_list():
            self.graph.add_node(peer.node_id, **{
                'address': peer.address,
                'port': peer.port,
                'reputation': peer.reputation,
                'capabilities': peer.capabilities
            })
        
        # Add edges based on current connections
        await self._add_connection_edges()
    
    async def _add_connection_edges(self):
        """Add edges for current peer connections"""
        peers = self.discovery.get_peer_list()
        
        # In a real implementation, this would use actual connection data
        # For now, create a mesh topology
        for i, peer1 in enumerate(peers):
            for peer2 in peers[i+1:]:
                if self._should_connect(peer1, peer2):
                    weight = await self._calculate_connection_weight(peer1, peer2)
                    self.graph.add_edge(peer1.node_id, peer2.node_id, weight=weight)
    
    def _should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Determine if two peers should be connected"""
        # Check degree constraints
        if (self.graph.degree(peer1.node_id) >= self.max_degree or 
            self.graph.degree(peer2.node_id) >= self.max_degree):
            return False
        
        # Check strategy-specific rules
        if self.strategy == TopologyStrategy.SMALL_WORLD:
            return self._small_world_should_connect(peer1, peer2)
        elif self.strategy == TopologyStrategy.SCALE_FREE:
            return self._scale_free_should_connect(peer1, peer2)
        elif self.strategy == TopologyStrategy.MESH:
            return self._mesh_should_connect(peer1, peer2)
        elif self.strategy == TopologyStrategy.HYBRID:
            return self._hybrid_should_connect(peer1, peer2)
        
        return False
    
    def _small_world_should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Small world topology connection logic"""
        # Connect to nearby peers and some random long-range connections
        import random
        
        if random.random() < 0.1:  # 10% random connections
            return True
        
        # Connect based on geographic or network proximity (simplified)
        return random.random() < 0.3  # 30% of nearby connections
    
    def _scale_free_should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Scale-free topology connection logic"""
        # Prefer connecting to high-degree nodes (rich-get-richer)
        degree1 = self.graph.degree(peer1.node_id)
        degree2 = self.graph.degree(peer2.node_id)
        
        # Higher probability for nodes with higher degree
        connection_probability = (degree1 + degree2) / (2 * self.max_degree)
        return random.random() < connection_probability
    
    def _mesh_should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Full mesh topology connection logic"""
        # Connect to all peers (within degree limits)
        return True
    
    def _hybrid_should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Hybrid topology connection logic"""
        # Combine multiple strategies
        import random
        
        # 40% small world, 30% scale-free, 30% mesh
        strategy_choice = random.random()
        
        if strategy_choice < 0.4:
            return self._small_world_should_connect(peer1, peer2)
        elif strategy_choice < 0.7:
            return self._scale_free_should_connect(peer1, peer2)
        else:
            return self._mesh_should_connect(peer1, peer2)
    
    async def _calculate_connection_weight(self, peer1: PeerNode, peer2: PeerNode) -> float:
        """Calculate connection weight between two peers"""
        # Get health metrics
        health1 = self.health_monitor.get_health_status(peer1.node_id)
        health2 = self.health_monitor.get_health_status(peer2.node_id)
        
        # Calculate weight based on health, reputation, and performance
        weight = 1.0
        
        if health1 and health2:
            # Factor in health scores
            weight *= (health1.health_score + health2.health_score) / 2
        
        # Factor in reputation
        weight *= (peer1.reputation + peer2.reputation) / 2
        
        # Factor in latency (inverse relationship)
        if health1 and health1.latency_ms > 0:
            weight *= min(1.0, 1000 / health1.latency_ms)
        
        return max(0.1, weight)  # Minimum weight of 0.1
    
    async def _optimize_topology(self):
        """Optimize network topology"""
        log_info("Optimizing network topology")
        
        # Analyze current topology
        await self._analyze_topology()
        
        # Identify optimization opportunities
        improvements = await self._identify_improvements()
        
        # Apply improvements
        for improvement in improvements:
            await self._apply_improvement(improvement)
    
    async def _analyze_topology(self):
        """Analyze current network topology"""
        if len(self.graph.nodes()) == 0:
            return
        
        # Calculate basic metrics
        if nx.is_connected(self.graph):
            self.avg_path_length = nx.average_shortest_path_length(self.graph, weight='weight')
        else:
            self.avg_path_length = float('inf')
        
        self.clustering_coefficient = nx.average_clustering(self.graph)
        
        # Calculate network efficiency
        self.network_efficiency = nx.global_efficiency(self.graph)
        
        log_info(f"Topology metrics - Path length: {self.avg_path_length:.2f}, "
                f"Clustering: {self.clustering_coefficient:.2f}, "
                f"Efficiency: {self.network_efficiency:.2f}")
    
    async def _identify_improvements(self) -> List[Dict]:
        """Identify topology improvements"""
        improvements = []
        
        # Check for disconnected nodes
        if not nx.is_connected(self.graph):
            components = list(nx.connected_components(self.graph))
            if len(components) > 1:
                improvements.append({
                    'type': 'connect_components',
                    'components': components
                })
        
        # Check degree distribution
        degrees = dict(self.graph.degree())
        low_degree_nodes = [node for node, degree in degrees.items() if degree < self.min_degree]
        high_degree_nodes = [node for node, degree in degrees.items() if degree > self.max_degree]
        
        if low_degree_nodes:
            improvements.append({
                'type': 'increase_degree',
                'nodes': low_degree_nodes
            })
        
        if high_degree_nodes:
            improvements.append({
                'type': 'decrease_degree',
                'nodes': high_degree_nodes
            })
        
        # Check for inefficient paths
        if self.avg_path_length > 6:  # Too many hops
            improvements.append({
                'type': 'add_shortcuts',
                'target_path_length': 4
            })
        
        return improvements
    
    async def _apply_improvement(self, improvement: Dict):
        """Apply topology improvement"""
        improvement_type = improvement['type']
        
        if improvement_type == 'connect_components':
            await self._connect_components(improvement['components'])
        elif improvement_type == 'increase_degree':
            await self._increase_node_degree(improvement['nodes'])
        elif improvement_type == 'decrease_degree':
            await self._decrease_node_degree(improvement['nodes'])
        elif improvement_type == 'add_shortcuts':
            await self._add_shortcuts(improvement['target_path_length'])
    
    async def _connect_components(self, components: List[Set[str]]):
        """Connect disconnected components"""
        log_info(f"Connecting {len(components)} disconnected components")
        
        # Connect components by adding edges between representative nodes
        for i in range(len(components) - 1):
            component1 = list(components[i])
            component2 = list(components[i + 1])
            
            # Select best nodes to connect
            node1 = self._select_best_connection_node(component1)
            node2 = self._select_best_connection_node(component2)
            
            # Add connection
            if node1 and node2:
                peer1 = self.discovery.peers.get(node1)
                peer2 = self.discovery.peers.get(node2)
                
                if peer1 and peer2:
                    await self._establish_connection(peer1, peer2)
    
    async def _increase_node_degree(self, nodes: List[str]):
        """Increase degree of low-degree nodes"""
        for node_id in nodes:
            peer = self.discovery.peers.get(node_id)
            if not peer:
                continue
            
            # Find best candidates for connection
            candidates = await self._find_connection_candidates(peer, max_connections=2)
            
            for candidate_peer in candidates:
                await self._establish_connection(peer, candidate_peer)
    
    async def _decrease_node_degree(self, nodes: List[str]):
        """Decrease degree of high-degree nodes"""
        for node_id in nodes:
            # Remove lowest quality connections
            edges = list(self.graph.edges(node_id, data=True))
            
            # Sort by weight (lowest first)
            edges.sort(key=lambda x: x[2].get('weight', 1.0))
            
            # Remove excess connections
            excess_count = self.graph.degree(node_id) - self.max_degree
            for i in range(min(excess_count, len(edges))):
                edge = edges[i]
                await self._remove_connection(edge[0], edge[1])
    
    async def _add_shortcuts(self, target_path_length: float):
        """Add shortcut connections to reduce path length"""
        # Find pairs of nodes with long shortest paths
        all_pairs = dict(nx.all_pairs_shortest_path_length(self.graph))
        
        long_paths = []
        for node1, paths in all_pairs.items():
            for node2, distance in paths.items():
                if node1 != node2 and distance > target_path_length:
                    long_paths.append((node1, node2, distance))
        
        # Sort by path length (longest first)
        long_paths.sort(key=lambda x: x[2], reverse=True)
        
        # Add shortcuts for longest paths
        for node1_id, node2_id, _ in long_paths[:5]:  # Limit to 5 shortcuts
            peer1 = self.discovery.peers.get(node1_id)
            peer2 = self.discovery.peers.get(node2_id)
            
            if peer1 and peer2 and not self.graph.has_edge(node1_id, node2_id):
                await self._establish_connection(peer1, peer2)
    
    def _select_best_connection_node(self, nodes: List[str]) -> Optional[str]:
        """Select best node for inter-component connection"""
        best_node = None
        best_score = 0
        
        for node_id in nodes:
            peer = self.discovery.peers.get(node_id)
            if not peer:
                continue
            
            # Score based on reputation and health
            health = self.health_monitor.get_health_status(node_id)
            score = peer.reputation
            
            if health:
                score *= health.health_score
            
            if score > best_score:
                best_score = score
                best_node = node_id
        
        return best_node
    
    async def _find_connection_candidates(self, peer: PeerNode, max_connections: int = 3) -> List[PeerNode]:
        """Find best candidates for new connections"""
        candidates = []
        
        for candidate_peer in self.discovery.get_peer_list():
            if (candidate_peer.node_id == peer.node_id or 
                self.graph.has_edge(peer.node_id, candidate_peer.node_id)):
                continue
            
            # Score candidate
            score = await self._calculate_connection_weight(peer, candidate_peer)
            candidates.append((candidate_peer, score))
        
        # Sort by score and return top candidates
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [candidate for candidate, _ in candidates[:max_connections]]
    
    async def _establish_connection(self, peer1: PeerNode, peer2: PeerNode):
        """Establish connection between two peers"""
        try:
            # In a real implementation, this would establish actual network connection
            weight = await self._calculate_connection_weight(peer1, peer2)
            
            self.graph.add_edge(peer1.node_id, peer2.node_id, weight=weight)
            
            log_info(f"Established connection between {peer1.node_id} and {peer2.node_id}")
            
        except Exception as e:
            log_error(f"Failed to establish connection between {peer1.node_id} and {peer2.node_id}: {e}")
    
    async def _remove_connection(self, node1_id: str, node2_id: str):
        """Remove connection between two nodes"""
        try:
            if self.graph.has_edge(node1_id, node2_id):
                self.graph.remove_edge(node1_id, node2_id)
                log_info(f"Removed connection between {node1_id} and {node2_id}")
        except Exception as e:
            log_error(f"Failed to remove connection between {node1_id} and {node2_id}: {e}")
    
    def get_topology_metrics(self) -> Dict:
        """Get current topology metrics"""
        return {
            'node_count': len(self.graph.nodes()),
            'edge_count': len(self.graph.edges()),
            'avg_degree': sum(dict(self.graph.degree()).values()) / len(self.graph.nodes()) if self.graph.nodes() else 0,
            'avg_path_length': self.avg_path_length,
            'clustering_coefficient': self.clustering_coefficient,
            'network_efficiency': self.network_efficiency,
            'is_connected': nx.is_connected(self.graph),
            'strategy': self.strategy.value
        }
    
    def get_visualization_data(self) -> Dict:
        """Get data for network visualization"""
        nodes = []
        edges = []
        
        for node_id in self.graph.nodes():
            node_data = self.graph.nodes[node_id]
            peer = self.discovery.peers.get(node_id)
            
            nodes.append({
                'id': node_id,
                'address': node_data.get('address', ''),
                'reputation': node_data.get('reputation', 0),
                'degree': self.graph.degree(node_id)
            })
        
        for edge in self.graph.edges(data=True):
            edges.append({
                'source': edge[0],
                'target': edge[1],
                'weight': edge[2].get('weight', 1.0)
            })
        
        return {
            'nodes': nodes,
            'edges': edges
        }

# Global topology manager
topology_manager: Optional[NetworkTopology] = None

def get_topology_manager() -> Optional[NetworkTopology]:
    """Get global topology manager"""
    return topology_manager

def create_topology_manager(discovery: P2PDiscovery, health_monitor: PeerHealthMonitor) -> NetworkTopology:
    """Create and set global topology manager"""
    global topology_manager
    topology_manager = NetworkTopology(discovery, health_monitor)
    return topology_manager
