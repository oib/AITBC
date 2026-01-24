#!/usr/bin/env python3
"""
AITBC Blockchain Sync Monitor
Real-time monitoring of blockchain synchronization status
"""

import time
import json
import sys
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import threading
import signal

class SyncMonitor:
    def __init__(self, node_url: str = "http://localhost:8545"):
        """Initialize the sync monitor"""
        self.node_url = node_url
        self.running = False
        self.start_time = None
        self.last_block = 0
        self.sync_history = []
        self.max_history = 100
        
        # ANSI colors for terminal output
        self.colors = {
            'red': '\033[91m',
            'green': '\033[92m',
            'yellow': '\033[93m',
            'blue': '\033[94m',
            'magenta': '\033[95m',
            'cyan': '\033[96m',
            'white': '\033[97m',
            'end': '\033[0m'
        }
    
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
                timeout=5
            )
            return response.json().get('result')
        except Exception as e:
            return None
    
    def get_sync_status(self) -> Dict:
        """Get current sync status"""
        sync_result = self.rpc_call("eth_syncing")
        
        if sync_result is False:
            # Fully synced
            latest_block = self.rpc_call("eth_blockNumber")
            return {
                'syncing': False,
                'current_block': int(latest_block, 16) if latest_block else 0,
                'highest_block': int(latest_block, 16) if latest_block else 0,
                'sync_percent': 100.0
            }
        else:
            # Still syncing
            current = int(sync_result.get('currentBlock', '0x0'), 16)
            highest = int(sync_result.get('highestBlock', '0x0'), 16)
            percent = (current / highest * 100) if highest > 0 else 0
            
            return {
                'syncing': True,
                'current_block': current,
                'highest_block': highest,
                'sync_percent': percent,
                'starting_block': int(sync_result.get('startingBlock', '0x0'), 16),
                'pulled_states': sync_result.get('pulledStates', '0x0'),
                'known_states': sync_result.get('knownStates', '0x0')
            }
    
    def get_peer_count(self) -> int:
        """Get number of connected peers"""
        result = self.rpc_call("net_peerCount")
        return int(result, 16) if result else 0
    
    def get_block_time(self, block_number: int) -> Optional[datetime]:
        """Get block timestamp"""
        block = self.rpc_call("eth_getBlockByNumber", [hex(block_number), False])
        if block and 'timestamp' in block:
            return datetime.fromtimestamp(int(block['timestamp'], 16))
        return None
    
    def calculate_sync_speed(self) -> Optional[float]:
        """Calculate current sync speed (blocks/second)"""
        if len(self.sync_history) < 2:
            return None
        
        # Get last two data points
        recent = self.sync_history[-2:]
        blocks_diff = recent[1]['current_block'] - recent[0]['current_block']
        time_diff = (recent[1]['timestamp'] - recent[0]['timestamp']).total_seconds()
        
        if time_diff > 0:
            return blocks_diff / time_diff
        return None
    
    def estimate_time_remaining(self, current: int, target: int, speed: float) -> str:
        """Estimate time remaining to sync"""
        if speed <= 0:
            return "Unknown"
        
        blocks_remaining = target - current
        seconds_remaining = blocks_remaining / speed
        
        if seconds_remaining < 60:
            return f"{int(seconds_remaining)} seconds"
        elif seconds_remaining < 3600:
            return f"{int(seconds_remaining / 60)} minutes"
        elif seconds_remaining < 86400:
            return f"{int(seconds_remaining / 3600)} hours"
        else:
            return f"{int(seconds_remaining / 86400)} days"
    
    def print_status_bar(self, status: Dict):
        """Print a visual sync status bar"""
        width = 50
        filled = int(width * status['sync_percent'] / 100)
        bar = '█' * filled + '░' * (width - filled)
        
        color = self.colors['green'] if status['sync_percent'] > 90 else \
                self.colors['yellow'] if status['sync_percent'] > 50 else \
                self.colors['red']
        
        print(f"\r{color}[{bar}]{self.colors['end']} {status['sync_percent']:.2f}%", end='', flush=True)
    
    def print_detailed_status(self, status: Dict, speed: float, peers: int):
        """Print detailed sync information"""
        print(f"\n{'='*60}")
        print(f"{self.colors['cyan']}AITBC Blockchain Sync Monitor{self.colors['end']}")
        print(f"{'='*60}")
        
        # Sync status
        if status['syncing']:
            print(f"\n{self.colors['yellow']}Syncing...{self.colors['end']}")
        else:
            print(f"\n{self.colors['green']}Fully Synchronized!{self.colors['end']}")
        
        # Block information
        print(f"\n{self.colors['blue']}Block Information:{self.colors['end']}")
        print(f"  Current:  {status['current_block']:,}")
        print(f"  Highest:  {status['highest_block']:,}")
        print(f"  Progress: {status['sync_percent']:.2f}%")
        
        if status['syncing'] and speed:
            eta = self.estimate_time_remaining(
                status['current_block'],
                status['highest_block'],
                speed
            )
            print(f"  ETA:      {eta}")
        
        # Sync speed
        if speed:
            print(f"\n{self.colors['blue']}Sync Speed:{self.colors['end']}")
            print(f"  {speed:.2f} blocks/second")
            
            # Calculate blocks per minute/hour
            print(f"  {speed * 60:.0f} blocks/minute")
            print(f"  {speed * 3600:.0f} blocks/hour")
        
        # Network information
        print(f"\n{self.colors['blue']}Network:{self.colors['end']}")
        print(f"  Peers connected: {peers}")
        
        # State sync (if available)
        if status.get('pulled_states') and status.get('known_states'):
            pulled = int(status['pulled_states'], 16)
            known = int(status['known_states'], 16)
            if known > 0:
                state_percent = (pulled / known) * 100
                print(f"  State sync: {state_percent:.2f}%")
        
        # Time information
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            print(f"\n{self.colors['blue']}Time:{self.colors['end']}")
            print(f"  Started: {self.start_time.strftime('%H:%M:%S')}")
            print(f"  Elapsed: {str(elapsed).split('.')[0]}")
    
    def monitor_loop(self, interval: int = 5, detailed: bool = False):
        """Main monitoring loop"""
        self.running = True
        self.start_time = datetime.now()
        
        print(f"Starting sync monitor (interval: {interval}s)")
        print("Press Ctrl+C to stop\n")
        
        try:
            while self.running:
                # Get current status
                status = self.get_sync_status()
                peers = self.get_peer_count()
                
                # Add to history
                status['timestamp'] = datetime.now()
                self.sync_history.append(status)
                if len(self.sync_history) > self.max_history:
                    self.sync_history.pop(0)
                
                # Calculate sync speed
                speed = self.calculate_sync_speed()
                
                # Display
                if detailed:
                    self.print_detailed_status(status, speed, peers)
                else:
                    self.print_status_bar(status)
                
                # Check if fully synced
                if not status['syncing']:
                    if not detailed:
                        print()  # New line after status bar
                    print(f"\n{self.colors['green']}✓ Sync completed!{self.colors['end']}")
                    break
                
                # Wait for next interval
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.running = False
            print(f"\n\n{self.colors['yellow']}Sync monitor stopped by user{self.colors['end']}")
        
        # Print final summary
        self.print_summary()
    
    def print_summary(self):
        """Print sync summary"""
        if not self.sync_history:
            return
        
        print(f"\n{self.colors['cyan']}Sync Summary{self.colors['end']}")
        print("-" * 40)
        
        if self.start_time:
            total_time = datetime.now() - self.start_time
            print(f"Total time: {str(total_time).split('.')[0]}")
        
        if len(self.sync_history) >= 2:
            blocks_synced = self.sync_history[-1]['current_block'] - self.sync_history[0]['current_block']
            print(f"Blocks synced: {blocks_synced:,}")
            
            if total_time.total_seconds() > 0:
                avg_speed = blocks_synced / total_time.total_seconds()
                print(f"Average speed: {avg_speed:.2f} blocks/second")
    
    def save_report(self, filename: str):
        """Save sync report to file"""
        report = {
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': datetime.now().isoformat(),
            'sync_history': [
                {
                    'timestamp': entry['timestamp'].isoformat(),
                    'current_block': entry['current_block'],
                    'highest_block': entry['highest_block'],
                    'sync_percent': entry['sync_percent']
                }
                for entry in self.sync_history
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Report saved to: {filename}")

def signal_handler(signum, frame):
    """Handle Ctrl+C"""
    print("\n\nStopping sync monitor...")
    sys.exit(0)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='AITBC Blockchain Sync Monitor')
    parser.add_argument('--node', default='http://localhost:8545', help='Node URL')
    parser.add_argument('--interval', type=int, default=5, help='Update interval (seconds)')
    parser.add_argument('--detailed', action='store_true', help='Show detailed output')
    parser.add_argument('--report', help='Save report to file')
    
    args = parser.parse_args()
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create and run monitor
    monitor = SyncMonitor(args.node)
    
    try:
        monitor.monitor_loop(interval=args.interval, detailed=args.detailed)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Save report if requested
    if args.report:
        monitor.save_report(args.report)

if __name__ == "__main__":
    main()
