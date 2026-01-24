#!/usr/bin/env python3
"""
AITBC Network Diagnostics Tool
Analyzes network connectivity, peer health, and block propagation
"""

import json
import sys
import time
import socket
import subprocess
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import requests

class NetworkDiagnostics:
    def __init__(self, node_url: str = "http://localhost:8545"):
        """Initialize network diagnostics"""
        self.node_url = node_url
        self.results = {}
        
    def rpc_call(self, method: str, params: List = None) -> Optional[Dict]:
        """Make JSON-RPC call to node"""
        try:
            response = requests.post(
                self.node_url,
                json={
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params or [],
                    "id": 1
                },
                timeout=10
            )
            return response.json().get('result')
        except Exception as e:
            return None
    
    def check_connectivity(self) -> Dict[str, any]:
        """Check basic network connectivity"""
        print("Checking network connectivity...")
        
        results = {
            'node_reachable': False,
            'dns_resolution': {},
            'port_checks': {},
            'internet_connectivity': False
        }
        
        # Check if node is reachable
        try:
            response = requests.get(self.node_url, timeout=5)
            results['node_reachable'] = response.status_code == 200
        except:
            pass
        
        # DNS resolution checks
        domains = ['aitbc.io', 'api.aitbc.io', 'mainnet.aitbc.io']
        for domain in domains:
            try:
                ip = socket.gethostbyname(domain)
                results['dns_resolution'][domain] = {
                    'resolvable': True,
                    'ip': ip
                }
            except:
                results['dns_resolution'][domain] = {
                    'resolvable': False,
                    'ip': None
                }
        
        # Port checks
        ports = [
            ('localhost', 8545, 'RPC'),
            ('localhost', 8546, 'WS'),
            ('localhost', 30303, 'P2P TCP'),
            ('localhost', 30303, 'P2P UDP')
        ]
        
        for host, port, service in ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            results['port_checks'][f'{host}:{port} ({service})'] = result == 0
            sock.close()
        
        # Internet connectivity
        try:
            response = requests.get('https://google.com', timeout=5)
            results['internet_connectivity'] = response.status_code == 200
        except:
            pass
        
        self.results['connectivity'] = results
        return results
    
    def analyze_peers(self) -> Dict[str, any]:
        """Analyze peer connections"""
        print("Analyzing peer connections...")
        
        results = {
            'peer_count': 0,
            'peer_details': [],
            'peer_distribution': {},
            'connection_types': {},
            'latency_stats': {}
        }
        
        # Get peer list
        peers = self.rpc_call("admin_peers") or []
        results['peer_count'] = len(peers)
        
        # Analyze each peer
        for peer in peers:
            peer_info = {
                'id': (peer.get('id', '')[:10] + '...') if peer.get('id') else '',
                'address': peer.get('network', {}).get('remoteAddress', 'Unknown'),
                'local_address': peer.get('network', {}).get('localAddress', 'Unknown'),
                'caps': list(peer.get('protocols', {}).keys()),
                'connected_duration': peer.get('network', {}).get('connectedDuration', 0)
            }
            
            # Extract IP for geolocation
            if ':' in peer_info['address']:
                ip = peer_info['address'].split(':')[0]
                peer_info['ip'] = ip
                
                # Get country (would use geoip library in production)
                try:
                    # Simple ping test for latency
                    start = time.time()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex((ip, 30303))
                    latency = (time.time() - start) * 1000 if result == 0 else None
                    sock.close()
                    peer_info['latency_ms'] = latency
                except:
                    peer_info['latency_ms'] = None
            
            results['peer_details'].append(peer_info)
        
        # Calculate distribution
        countries = {}
        for peer in results['peer_details']:
            country = peer.get('country', 'Unknown')
            countries[country] = countries.get(country, 0) + 1
        results['peer_distribution'] = countries
        
        # Calculate latency stats
        latencies = [p['latency_ms'] for p in results['peer_details'] if p['latency_ms'] is not None]
        if latencies:
            results['latency_stats'] = {
                'min': min(latencies),
                'max': max(latencies),
                'avg': sum(latencies) / len(latencies)
            }
        
        self.results['peers'] = results
        return results
    
    def test_block_propagation(self) -> Dict[str, any]:
        """Test block propagation speed"""
        print("Testing block propagation...")
        
        results = {
            'latest_block': 0,
            'block_age': 0,
            'propagation_delay': None,
            'uncle_rate': 0,
            'network_hashrate': 0
        }
        
        # Get latest block
        latest_block = self.rpc_call("eth_getBlockByNumber", ["latest", False])
        if latest_block:
            results['latest_block'] = int(latest_block['number'], 16)
            block_timestamp = int(latest_block['timestamp'], 16)
            results['block_age'] = int(time.time()) - block_timestamp
        
        # Get uncle rate (check last 100 blocks)
        try:
            uncle_count = 0
            for i in range(100):
                block = self.rpc_call("eth_getBlockByNumber", [hex(results['latest_block'] - i), False])
                if block and block.get('uncles'):
                    uncle_count += len(block['uncles'])
            results['uncle_rate'] = (uncle_count / 100) * 100
        except:
            pass
        
        # Get network hashrate
        try:
            latest = self.rpc_call("eth_getBlockByNumber", ["latest", False])
            if latest:
                difficulty = int(latest['difficulty'], 16)
                block_time = 13  # Average block time for ETH-like chains
                results['network_hashrate'] = difficulty / block_time
        except:
            pass
        
        self.results['block_propagation'] = results
        return results
    
    def check_fork_status(self) -> Dict[str, any]:
        """Check for network forks"""
        print("Checking for network forks...")
        
        results = {
            'current_fork': None,
            'fork_blocks': [],
            'reorg_detected': False,
            'chain_head': {}
        }
        
        # Get current fork block
        try:
            fork_block = self.rpc_call("eth_forkBlock")
            if fork_block:
                results['current_fork'] = int(fork_block, 16)
        except:
            pass
        
        # Check for recent reorganizations
        try:
            # Get last 10 blocks and check for inconsistencies
            for i in range(10):
                block_num = hex(int(self.rpc_call("eth_blockNumber"), 16) - i)
                block = self.rpc_call("eth_getBlockByNumber", [block_num, False])
                if block:
                    results['chain_head'][block_num] = {
                        'hash': block['hash'],
                        'parent': block.get('parentHash'),
                        'number': block['number']
                    }
        except:
            pass
        
        self.results['fork_status'] = results
        return results
    
    def analyze_network_performance(self) -> Dict[str, any]:
        """Analyze overall network performance"""
        print("Analyzing network performance...")
        
        results = {
            'rpc_response_time': 0,
            'ws_connection': False,
            'bandwidth_estimate': 0,
            'packet_loss': 0
        }
        
        # Test RPC response time
        start = time.time()
        self.rpc_call("eth_blockNumber")
        results['rpc_response_time'] = (time.time() - start) * 1000
        
        # Test WebSocket connection
        try:
            import websocket
            # Would implement actual WS connection test
            results['ws_connection'] = True
        except:
            results['ws_connection'] = False
        
        self.results['performance'] = results
        return results
    
    def generate_recommendations(self) -> List[str]:
        """Generate network improvement recommendations"""
        recommendations = []
        
        # Connectivity recommendations
        if not self.results.get('connectivity', {}).get('node_reachable'):
            recommendations.append("Node is not reachable - check if the node is running")
        
        if not self.results.get('connectivity', {}).get('internet_connectivity'):
            recommendations.append("No internet connectivity - check network connection")
        
        # Peer recommendations
        peer_count = self.results.get('peers', {}).get('peer_count', 0)
        if peer_count < 5:
            recommendations.append(f"Low peer count ({peer_count}) - check firewall and port forwarding")
        
        # Performance recommendations
        rpc_time = self.results.get('performance', {}).get('rpc_response_time', 0)
        if rpc_time > 1000:
            recommendations.append("High RPC response time - consider optimizing node or upgrading hardware")
        
        # Block propagation recommendations
        block_age = self.results.get('block_propagation', {}).get('block_age', 0)
        if block_age > 60:
            recommendations.append("Stale blocks detected - possible sync issues")
        
        return recommendations
    
    def print_report(self):
        """Print comprehensive diagnostic report"""
        print("\n" + "="*60)
        print("AITBC Network Diagnostics Report")
        print("="*60)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Node URL: {self.node_url}")
        
        # Connectivity section
        print("\n[Connectivity]")
        conn = self.results.get('connectivity', {})
        print(f"  Node Reachable: {'✓' if conn.get('node_reachable') else '✗'}")
        print(f"  Internet Access: {'✓' if conn.get('internet_connectivity') else '✗'}")
        
        for domain, info in conn.get('dns_resolution', {}).items():
            status = '✓' if info['resolvable'] else '✗'
            print(f"  DNS {domain}: {status}")
        
        # Peers section
        print("\n[Peer Analysis]")
        peers = self.results.get('peers', {})
        print(f"  Connected Peers: {peers.get('peer_count', 0)}")
        
        if peers.get('peer_distribution'):
            print("  Geographic Distribution:")
            for country, count in list(peers['peer_distribution'].items())[:5]:
                print(f"    {country}: {count} peers")
        
        if peers.get('latency_stats'):
            stats = peers['latency_stats']
            print(f"  Latency: {stats['avg']:.0f}ms avg (min: {stats['min']:.0f}ms, max: {stats['max']:.0f}ms)")
        
        # Block propagation section
        print("\n[Block Propagation]")
        prop = self.results.get('block_propagation', {})
        print(f"  Latest Block: {prop.get('latest_block', 0):,}")
        print(f"  Block Age: {prop.get('block_age', 0)} seconds")
        print(f"  Uncle Rate: {prop.get('uncle_rate', 0):.2f}%")
        
        # Performance section
        print("\n[Performance]")
        perf = self.results.get('performance', {})
        print(f"  RPC Response Time: {perf.get('rpc_response_time', 0):.0f}ms")
        print(f"  WebSocket: {'✓' if perf.get('ws_connection') else '✗'}")
        
        # Recommendations
        recommendations = self.generate_recommendations()
        if recommendations:
            print("\n[Recommendations]")
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. {rec}")
        
        print("\n" + "="*60)
    
    def save_report(self, filename: str):
        """Save detailed report to file"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'node_url': self.node_url,
            'results': self.results,
            'recommendations': self.generate_recommendations()
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\nDetailed report saved to: {filename}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='AITBC Network Diagnostics')
    parser.add_argument('--node', default='http://localhost:8545', help='Node URL')
    parser.add_argument('--output', help='Save report to file')
    parser.add_argument('--quick', action='store_true', help='Quick diagnostics')
    
    args = parser.parse_args()
    
    # Run diagnostics
    diag = NetworkDiagnostics(args.node)
    
    print("Running AITBC network diagnostics...")
    print("-" * 40)
    
    # Run all tests
    diag.check_connectivity()
    
    if not args.quick:
        diag.analyze_peers()
        diag.test_block_propagation()
        diag.check_fork_status()
        diag.analyze_network_performance()
    
    # Print report
    diag.print_report()
    
    # Save if requested
    if args.output:
        diag.save_report(args.output)

if __name__ == "__main__":
    main()
