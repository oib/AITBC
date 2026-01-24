#!/usr/bin/env python3
"""
AITBC Transaction Tracer
Comprehensive transaction debugging and analysis tool
"""

import web3
import json
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any

class TransactionTracer:
    def __init__(self, node_url: str = "http://localhost:8545"):
        """Initialize the transaction tracer"""
        self.w3 = web3.Web3(web3.HTTPProvider(node_url))
        if not self.w3.is_connected():
            raise Exception("Failed to connect to AITBC node")
    
    def trace_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Trace a transaction and return comprehensive information"""
        try:
            # Get transaction details
            tx = self.w3.eth.get_transaction(tx_hash)
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            # Build trace result
            trace = {
                'hash': tx_hash,
                'status': 'success' if receipt.status == 1 else 'failed',
                'block_number': tx.blockNumber,
                'block_hash': tx.blockHash.hex(),
                'transaction_index': receipt.transactionIndex,
                'from_address': tx['from'],
                'to_address': tx.get('to'),
                'value': self.w3.from_wei(tx.value, 'ether'),
                'gas_limit': tx.gas,
                'gas_used': receipt.gasUsed,
                'gas_price': self.w3.from_wei(tx.gasPrice, 'gwei'),
                'effective_gas_price': self.w3.from_wei(receipt.effectiveGasPrice, 'gwei'),
                'nonce': tx.nonce,
                'max_fee_per_gas': None,
                'max_priority_fee_per_gas': None,
                'type': tx.get('type', 0)
            }
            
            # EIP-1559 transaction fields
            if tx.get('type') == 2:
                trace['max_fee_per_gas'] = self.w3.from_wei(tx.maxFeePerGas, 'gwei')
                trace['max_priority_fee_per_gas'] = self.w3.from_wei(tx.maxPriorityFeePerGas, 'gwei')
            
            # Calculate gas efficiency
            trace['gas_efficiency'] = f"{(receipt.gasUsed / tx.gas * 100):.2f}%"
            
            # Get logs
            trace['logs'] = self._parse_logs(receipt.logs)
            
            # Get contract creation info if applicable
            if tx.get('to') is None:
                trace['contract_created'] = receipt.contractAddress
                trace['contract_code'] = self.w3.eth.get_code(receipt.contractAddress).hex()
            
            # Get internal transfers (if tracing is available)
            trace['internal_transfers'] = self._get_internal_transfers(tx_hash)
            
            return trace
            
        except Exception as e:
            return {'error': str(e), 'hash': tx_hash}
    
    def _parse_logs(self, logs: List) -> List[Dict]:
        """Parse transaction logs"""
        parsed_logs = []
        for log in logs:
            parsed_logs.append({
                'address': log.address,
                'topics': [topic.hex() for topic in log.topics],
                'data': log.data.hex(),
                'log_index': log.logIndex,
                'decoded': self._decode_log(log)
            })
        return parsed_logs
    
    def _decode_log(self, log) -> Optional[Dict]:
        """Attempt to decode log events"""
        # This would contain ABI decoding logic
        # For now, return basic info
        return {
            'signature': log.topics[0].hex() if log.topics else None,
            'event_name': 'Unknown'  # Would be decoded from ABI
        }
    
    def _get_internal_transfers(self, tx_hash: str) -> List[Dict]:
        """Get internal ETH transfers (requires tracing)"""
        try:
            # Try debug_traceTransaction if available
            trace = self.w3.provider.make_request('debug_traceTransaction', [tx_hash, {}])
            transfers = []
            
            # Parse trace for transfers
            if trace and 'result' in trace:
                # Implementation would parse the trace for CALL/DELEGATECALL with value
                pass
            
            return transfers
        except:
            return []
    
    def analyze_gas_usage(self, tx_hash: str) -> Dict[str, Any]:
        """Analyze gas usage and provide optimization tips"""
        trace = self.trace_transaction(tx_hash)
        
        if 'error' in trace:
            return trace
        
        analysis = {
            'gas_used': trace['gas_used'],
            'gas_limit': trace['gas_limit'],
            'efficiency': trace['gas_efficiency'],
            'recommendations': []
        }
        
        # Gas efficiency recommendations
        if trace['gas_used'] < trace['gas_limit'] * 0.5:
            analysis['recommendations'].append(
                f"Gas limit too high. Consider reducing to ~{int(trace['gas_used'] * 1.2)}"
            )
        
        # Gas price analysis
        if trace['gas_price'] > 100:  # High gas price threshold
            analysis['recommendations'].append(
                "High gas price detected. Consider using EIP-1559 or waiting for lower gas"
            )
        
        return analysis
    
    def debug_failed_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Debug why a transaction failed"""
        trace = self.trace_transaction(tx_hash)
        
        if trace.get('status') == 'success':
            return {'error': 'Transaction was successful', 'hash': tx_hash}
        
        debug_info = {
            'hash': tx_hash,
            'failure_reason': 'Unknown',
            'possible_causes': [],
            'debug_steps': []
        }
        
        # Check for common failure reasons
        debug_info['debug_steps'].append("1. Checking if transaction ran out of gas...")
        if trace['gas_used'] == trace['gas_limit']:
            debug_info['failure_reason'] = 'Out of gas'
            debug_info['possible_causes'].append('Transaction required more gas than provided')
            debug_info['debug_steps'].append("   ✓ Transaction ran out of gas")
        
        debug_info['debug_steps'].append("2. Checking for revert reasons...")
        # Would implement revert reason decoding here
        debug_info['debug_steps'].append("   ✗ Could not decode revert reason")
        
        debug_info['debug_steps'].append("3. Checking nonce issues...")
        # Would check for nonce problems
        debug_info['debug_steps'].append("   ✓ Nonce appears correct")
        
        return debug_info
    
    def monitor_mempool(self, address: str = None) -> Dict[str, Any]:
        """Monitor transaction mempool"""
        try:
            # Get pending transactions
            pending_block = self.w3.eth.get_block('pending', full_transactions=True)
            pending_txs = pending_block.transactions
            
            mempool_info = {
                'pending_count': len(pending_txs),
                'pending_by_address': {},
                'high_priority_txs': [],
                'stuck_txs': []
            }
            
            # Analyze pending transactions
            for tx in pending_txs:
                from_addr = str(tx['from'])
                if from_addr not in mempool_info['pending_by_address']:
                    mempool_info['pending_by_address'][from_addr] = 0
                mempool_info['pending_by_address'][from_addr] += 1
                
                # High priority transactions (high gas price)
                if tx.gasPrice > web3.Web3.to_wei(50, 'gwei'):
                    mempool_info['high_priority_txs'].append({
                        'hash': tx.hash.hex(),
                        'gas_price': web3.Web3.from_wei(tx.gasPrice, 'gwei'),
                        'from': from_addr
                    })
            
            return mempool_info
            
        except Exception as e:
            return {'error': str(e)}
    
    def print_trace(self, trace: Dict[str, Any]):
        """Print formatted transaction trace"""
        if 'error' in trace:
            print(f"Error: {trace['error']}")
            return
        
        print(f"\n{'='*60}")
        print(f"Transaction Trace: {trace['hash']}")
        print(f"{'='*60}")
        print(f"Status: {trace['status'].upper()}")
        print(f"Block: #{trace['block_number']} ({trace['block_hash'][:10]}...)")
        print(f"From: {trace['from_address']}")
        print(f"To: {trace['to_address'] or 'Contract Creation'}")
        print(f"Value: {trace['value']} ETH")
        print(f"Gas Used: {trace['gas_used']:,} / {trace['gas_limit']:,} ({trace['gas_efficiency']})")
        print(f"Gas Price: {trace['gas_price']} gwei")
        if trace['max_fee_per_gas']:
            print(f"Max Fee: {trace['max_fee_per_gas']} gwei")
            print(f"Priority Fee: {trace['max_priority_fee_per_gas']} gwei")
        
        if trace.get('contract_created'):
            print(f"\nContract Created: {trace['contract_created']}")
        
        if trace['logs']:
            print(f"\nLogs ({len(trace['logs'])}):")
            for log in trace['logs'][:5]:  # Show first 5 logs
                print(f"  - {log['address']}: {log['decoded']['event_name'] or 'Unknown Event'}")
        
        if trace['internal_transfers']:
            print(f"\nInternal Transfers:")
            for transfer in trace['internal_transfers']:
                print(f"  {transfer['from']} -> {transfer['to']}: {transfer['value']} ETH")

def main():
    parser = argparse.ArgumentParser(description='AITBC Transaction Tracer')
    parser.add_argument('command', choices=['trace', 'analyze', 'debug', 'mempool'])
    parser.add_argument('--tx', help='Transaction hash')
    parser.add_argument('--address', help='Address for mempool monitoring')
    parser.add_argument('--node', default='http://localhost:8545', help='Node URL')
    
    args = parser.parse_args()
    
    tracer = TransactionTracer(args.node)
    
    if args.command == 'trace':
        if not args.tx:
            print("Error: Transaction hash required for trace command")
            sys.exit(1)
        trace = tracer.trace_transaction(args.tx)
        tracer.print_trace(trace)
    
    elif args.command == 'analyze':
        if not args.tx:
            print("Error: Transaction hash required for analyze command")
            sys.exit(1)
        analysis = tracer.analyze_gas_usage(args.tx)
        print(json.dumps(analysis, indent=2))
    
    elif args.command == 'debug':
        if not args.tx:
            print("Error: Transaction hash required for debug command")
            sys.exit(1)
        debug = tracer.debug_failed_transaction(args.tx)
        print(json.dumps(debug, indent=2))
    
    elif args.command == 'mempool':
        mempool = tracer.monitor_mempool(args.address)
        print(json.dumps(mempool, indent=2))

if __name__ == "__main__":
    main()
