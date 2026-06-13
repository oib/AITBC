"""
Message storage layer for persisting agent communication messages in Redis
"""
import json
from datetime import UTC, datetime
from typing import Any
from aitbc import get_logger
logger = get_logger(__name__)

class MessageStorage:
    """Redis-based message storage for agent communication history"""

    def __init__(self, redis_url: str) -> None:
        """Initialize message storage with Redis connection"""
        import redis.asyncio as redis
        self.redis_url = redis_url
        self.redis: redis.Redis | None = None

    async def start(self) -> None:
        """Connect to Redis"""
        import redis.asyncio as redis
        self.redis = await redis.from_url(self.redis_url, decode_responses=True)
        logger.info('Message storage connected to Redis')

    async def stop(self) -> None:
        """Close Redis connection"""
        if self.redis:
            await self.redis.aclose()
            logger.info('Message storage disconnected from Redis')

    async def store_message(self, message_id: str, message_data: dict[str, Any]) -> bool:
        """Store a message in Redis"""
        try:
            await self.redis.hset(f'message:{message_id}', mapping=message_data)
            sender_id = message_data.get('sender')
            if sender_id:
                await self.redis.sadd(f'messages:sender:{sender_id}', message_id)
            receiver_id = message_data.get('recipient')
            if receiver_id:
                await self.redis.sadd(f'messages:receiver:{receiver_id}', message_id)
            timestamp_str = message_data.get('timestamp', datetime.now(UTC).isoformat())
            try:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                timestamp_float = dt.timestamp()
            except Exception:
                timestamp_float = float(timestamp_str)
            await self.redis.zadd('messages:timestamp', {message_id: timestamp_float})
            logger.debug('Stored message %s in Redis', message_id)
            return True
        except Exception as e:
            logger.error('Error storing message %s: %s', message_id, e)
            return False

    async def get_message_count(self) -> int:
        """Get total count of messages"""
        try:
            return await self.redis.zcard('messages:timestamp')
        except Exception as e:
            logger.error('Error getting message count: %s', e)
            return 0

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        """Retrieve a specific message by ID"""
        try:
            message_data = await self.redis.hgetall(f'message:{message_id}')
            if message_data:
                if 'payload' in message_data:
                    message_data['payload'] = json.loads(message_data['payload'])
                return message_data
            return None
        except Exception as e:
            logger.error('Error retrieving message %s: %s', message_id, e)
            return None

    async def get_messages_by_sender(self, sender_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get messages sent by a specific agent"""
        try:
            message_ids = await self.redis.smembers(f'messages:sender:{sender_id}')
            message_ids = list(message_ids)
            message_ids = message_ids[offset:offset + limit]
            messages = []
            for message_id in message_ids:
                message_data = await self.get_message(message_id)
                if message_data:
                    messages.append(message_data)
            return messages
        except Exception as e:
            logger.error('Error retrieving messages for sender %s: %s', sender_id, e)
            return []

    async def get_messages_by_receiver(self, receiver_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get messages received by a specific agent"""
        try:
            message_ids = await self.redis.smembers(f'messages:receiver:{receiver_id}')
            message_ids = list(message_ids)
            message_ids = message_ids[offset:offset + limit]
            messages = []
            for message_id in message_ids:
                message_data = await self.get_message(message_id)
                if message_data:
                    messages.append(message_data)
            return messages
        except Exception as e:
            logger.error('Error retrieving messages for receiver %s: %s', receiver_id, e)
            return []

    async def get_all_messages(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get all messages with pagination"""
        try:
            message_ids = await self.redis.zrevrange('messages:timestamp', offset, offset + limit - 1)
            messages = []
            for message_id in message_ids:
                message_data = await self.get_message(message_id)
                if message_data:
                    messages.append(message_data)
            return messages
        except Exception as e:
            logger.error('Error retrieving all messages: %s', e)
            return []

    async def delete_message(self, message_id: str) -> bool:
        """Delete a specific message"""
        try:
            message_data = await self.get_message(message_id)
            if not message_data:
                return False
            sender_id = message_data.get('sender_id')
            if sender_id:
                await self.redis.srem(f'messages:sender:{sender_id}', message_id)
            receiver_id = message_data.get('receiver_id')
            if receiver_id:
                await self.redis.srem(f'messages:receiver:{receiver_id}', message_id)
            await self.redis.zrem('messages:timestamp', message_id)
            await self.redis.delete(f'message:{message_id}')
            logger.debug('Deleted message %s from Redis', message_id)
            return True
        except Exception as e:
            logger.error('Error deleting message %s: %s', message_id, e)
            return False

class PeerStorage:
    """Redis-based peer storage for persisting peer connections across restarts"""

    def __init__(self, redis_url: str) -> None:
        """Initialize peer storage with Redis connection"""
        import redis.asyncio as redis
        self.redis_url = redis_url
        self.redis: redis.Redis | None = None

    async def start(self) -> None:
        """Connect to Redis"""
        import redis.asyncio as redis
        self.redis = await redis.from_url(self.redis_url, decode_responses=True)
        logger.info('Peer storage connected to Redis')

    async def stop(self) -> None:
        """Close Redis connection"""
        if self.redis:
            await self.redis.aclose()
            logger.info('Peer storage disconnected from Redis')

    async def add_peer(self, agent_id: str, peer_id: str, metadata: dict[str, Any] | None = None) -> bool:
        """Add a peer connection for an agent"""
        try:
            await self.redis.sadd(f'peers:{agent_id}', peer_id)
            if metadata:
                await self.redis.hset(f'peer_connection:{agent_id}:{peer_id}', mapping=metadata)
            logger.debug('Added peer %s for agent %s', peer_id, agent_id)
            return True
        except Exception as e:
            logger.error('Error adding peer %s for agent %s: %s', peer_id, agent_id, e)
            return False

    async def remove_peer(self, agent_id: str, peer_id: str) -> bool:
        """Remove a peer connection for an agent"""
        try:
            await self.redis.srem(f'peers:{agent_id}', peer_id)
            await self.redis.delete(f'peer_connection:{agent_id}:{peer_id}')
            logger.debug('Removed peer %s for agent %s', peer_id, agent_id)
            return True
        except Exception as e:
            logger.error('Error removing peer %s for agent %s: %s', peer_id, agent_id, e)
            return False

    async def get_agent_peers(self, agent_id: str) -> list[str]:
        """Get all peers for a specific agent"""
        try:
            peer_ids = await self.redis.smembers(f'peers:{agent_id}')
            return list(peer_ids)
        except Exception as e:
            logger.error('Error retrieving peers for agent %s: %s', agent_id, e)
            return []

    async def get_peer_metadata(self, agent_id: str, peer_id: str) -> dict[str, Any] | None:
        """Get metadata for a specific peer connection"""
        try:
            metadata = await self.redis.hgetall(f'peer_connection:{agent_id}:{peer_id}')
            return metadata if metadata else None
        except Exception as e:
            logger.error('Error retrieving peer metadata for %s:%s: %s', agent_id, peer_id, e)
            return None

    async def get_all_peer_connections(self) -> dict[str, list[str]]:
        """Get all peer connections in the system"""
        try:
            peer_keys = await self.redis.keys('peers:*')
            connections = {}
            for key in peer_keys:
                agent_id = key.replace('peers:', '')
                peer_ids = await self.redis.smembers(key)
                connections[agent_id] = list(peer_ids)
            return connections
        except Exception as e:
            logger.error('Error retrieving all peer connections: %s', e)
            return {}