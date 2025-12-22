"""
Storage layer for cross-chain settlements
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import asyncio
from dataclasses import asdict

from .bridges.base import (
    SettlementMessage,
    SettlementResult,
    BridgeStatus
)


class SettlementStorage:
    """Storage interface for settlement data"""
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def store_settlement(
        self,
        message_id: str,
        message: SettlementMessage,
        bridge_name: str,
        status: BridgeStatus
    ) -> None:
        """Store a new settlement record"""
        query = """
        INSERT INTO settlements (
            message_id, job_id, source_chain_id, target_chain_id,
            receipt_hash, proof_data, payment_amount, payment_token,
            nonce, signature, bridge_name, status, created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
        )
        """
        
        await self.db.execute(query, (
            message_id,
            message.job_id,
            message.source_chain_id,
            message.target_chain_id,
            message.receipt_hash,
            json.dumps(message.proof_data),
            message.payment_amount,
            message.payment_token,
            message.nonce,
            message.signature,
            bridge_name,
            status.value,
            message.created_at or datetime.utcnow()
        ))
    
    async def update_settlement(
        self,
        message_id: str,
        status: Optional[BridgeStatus] = None,
        transaction_hash: Optional[str] = None,
        error_message: Optional[str] = None,
        completed_at: Optional[datetime] = None
    ) -> None:
        """Update settlement record"""
        updates = []
        params = []
        param_count = 1
        
        if status is not None:
            updates.append(f"status = ${param_count}")
            params.append(status.value)
            param_count += 1
        
        if transaction_hash is not None:
            updates.append(f"transaction_hash = ${param_count}")
            params.append(transaction_hash)
            param_count += 1
        
        if error_message is not None:
            updates.append(f"error_message = ${param_count}")
            params.append(error_message)
            param_count += 1
        
        if completed_at is not None:
            updates.append(f"completed_at = ${param_count}")
            params.append(completed_at)
            param_count += 1
        
        if not updates:
            return
        
        updates.append(f"updated_at = ${param_count}")
        params.append(datetime.utcnow())
        param_count += 1
        
        params.append(message_id)
        
        query = f"""
        UPDATE settlements 
        SET {', '.join(updates)}
        WHERE message_id = ${param_count}
        """
        
        await self.db.execute(query, params)
    
    async def get_settlement(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get settlement by message ID"""
        query = """
        SELECT * FROM settlements WHERE message_id = $1
        """
        
        result = await self.db.fetchrow(query, message_id)
        
        if not result:
            return None
        
        # Convert to dict
        settlement = dict(result)
        
        # Parse JSON fields
        if settlement['proof_data']:
            settlement['proof_data'] = json.loads(settlement['proof_data'])
        
        return settlement
    
    async def get_settlements_by_job(self, job_id: str) -> List[Dict[str, Any]]:
        """Get all settlements for a job"""
        query = """
        SELECT * FROM settlements 
        WHERE job_id = $1 
        ORDER BY created_at DESC
        """
        
        results = await self.db.fetch(query, job_id)
        
        settlements = []
        for result in results:
            settlement = dict(result)
            if settlement['proof_data']:
                settlement['proof_data'] = json.loads(settlement['proof_data'])
            settlements.append(settlement)
        
        return settlements
    
    async def get_pending_settlements(self, bridge_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all pending settlements"""
        query = """
        SELECT * FROM settlements 
        WHERE status = 'pending' OR status = 'in_progress'
        """
        params = []
        
        if bridge_name:
            query += " AND bridge_name = $1"
            params.append(bridge_name)
        
        query += " ORDER BY created_at ASC"
        
        results = await self.db.fetch(query, *params)
        
        settlements = []
        for result in results:
            settlement = dict(result)
            if settlement['proof_data']:
                settlement['proof_data'] = json.loads(settlement['proof_data'])
            settlements.append(settlement)
        
        return settlements
    
    async def get_settlement_stats(
        self,
        bridge_name: Optional[str] = None,
        time_range: Optional[int] = None  # hours
    ) -> Dict[str, Any]:
        """Get settlement statistics"""
        conditions = []
        params = []
        param_count = 1
        
        if bridge_name:
            conditions.append(f"bridge_name = ${param_count}")
            params.append(bridge_name)
            param_count += 1
        
        if time_range:
            conditions.append(f"created_at > NOW() - INTERVAL '${param_count} hours'")
            params.append(time_range)
            param_count += 1
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        query = f"""
        SELECT 
            bridge_name,
            status,
            COUNT(*) as count,
            AVG(payment_amount) as avg_amount,
            SUM(payment_amount) as total_amount
        FROM settlements 
        {where_clause}
        GROUP BY bridge_name, status
        """
        
        results = await self.db.fetch(query, *params)
        
        stats = {}
        for result in results:
            bridge = result['bridge_name']
            if bridge not in stats:
                stats[bridge] = {}
            
            stats[bridge][result['status']] = {
                'count': result['count'],
                'avg_amount': float(result['avg_amount']) if result['avg_amount'] else 0,
                'total_amount': float(result['total_amount']) if result['total_amount'] else 0
            }
        
        return stats
    
    async def cleanup_old_settlements(self, days: int = 30) -> int:
        """Clean up old completed settlements"""
        query = """
        DELETE FROM settlements 
        WHERE status IN ('completed', 'failed') 
        AND created_at < NOW() - INTERVAL $1 days
        """
        
        result = await self.db.execute(query, days)
        return result.split()[-1]  # Return number of deleted rows


# In-memory implementation for testing
class InMemorySettlementStorage(SettlementStorage):
    """In-memory storage implementation for testing"""
    
    def __init__(self):
        self.settlements: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def store_settlement(
        self,
        message_id: str,
        message: SettlementMessage,
        bridge_name: str,
        status: BridgeStatus
    ) -> None:
        async with self._lock:
            self.settlements[message_id] = {
                'message_id': message_id,
                'job_id': message.job_id,
                'source_chain_id': message.source_chain_id,
                'target_chain_id': message.target_chain_id,
                'receipt_hash': message.receipt_hash,
                'proof_data': message.proof_data,
                'payment_amount': message.payment_amount,
                'payment_token': message.payment_token,
                'nonce': message.nonce,
                'signature': message.signature,
                'bridge_name': bridge_name,
                'status': status.value,
                'created_at': message.created_at or datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
    
    async def update_settlement(
        self,
        message_id: str,
        status: Optional[BridgeStatus] = None,
        transaction_hash: Optional[str] = None,
        error_message: Optional[str] = None,
        completed_at: Optional[datetime] = None
    ) -> None:
        async with self._lock:
            if message_id not in self.settlements:
                return
            
            settlement = self.settlements[message_id]
            
            if status is not None:
                settlement['status'] = status.value
            if transaction_hash is not None:
                settlement['transaction_hash'] = transaction_hash
            if error_message is not None:
                settlement['error_message'] = error_message
            if completed_at is not None:
                settlement['completed_at'] = completed_at
            
            settlement['updated_at'] = datetime.utcnow()
    
    async def get_settlement(self, message_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return self.settlements.get(message_id)
    
    async def get_settlements_by_job(self, job_id: str) -> List[Dict[str, Any]]:
        async with self._lock:
            return [
                s for s in self.settlements.values()
                if s['job_id'] == job_id
            ]
    
    async def get_pending_settlements(self, bridge_name: Optional[str] = None) -> List[Dict[str, Any]]:
        async with self._lock:
            pending = [
                s for s in self.settlements.values()
                if s['status'] in ['pending', 'in_progress']
            ]
            
            if bridge_name:
                pending = [s for s in pending if s['bridge_name'] == bridge_name]
            
            return pending
    
    async def get_settlement_stats(
        self,
        bridge_name: Optional[str] = None,
        time_range: Optional[int] = None
    ) -> Dict[str, Any]:
        async with self._lock:
            stats = {}
            
            for settlement in self.settlements.values():
                if bridge_name and settlement['bridge_name'] != bridge_name:
                    continue
                
                # TODO: Implement time range filtering
                
                bridge = settlement['bridge_name']
                if bridge not in stats:
                    stats[bridge] = {}
                
                status = settlement['status']
                if status not in stats[bridge]:
                    stats[bridge][status] = {
                        'count': 0,
                        'avg_amount': 0,
                        'total_amount': 0
                    }
                
                stats[bridge][status]['count'] += 1
                stats[bridge][status]['total_amount'] += settlement['payment_amount']
            
            # Calculate averages
            for bridge_data in stats.values():
                for status_data in bridge_data.values():
                    if status_data['count'] > 0:
                        status_data['avg_amount'] = status_data['total_amount'] / status_data['count']
            
            return stats
    
    async def cleanup_old_settlements(self, days: int = 30) -> int:
        async with self._lock:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            to_delete = [
                msg_id for msg_id, settlement in self.settlements.items()
                if (
                    settlement['status'] in ['completed', 'failed'] and
                    settlement['created_at'] < cutoff
                )
            ]
            
            for msg_id in to_delete:
                del self.settlements[msg_id]
            
            return len(to_delete)
