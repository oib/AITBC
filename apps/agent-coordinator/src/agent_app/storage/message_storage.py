"""
Message storage layer for persisting agent communication messages.

Primary backend is Redis.  When Redis is unavailable, the layer falls back to
a local SQLite database so messages are still durably stored on the
 coordinator node.
"""

import json
import os
import time
from datetime import UTC, datetime
from typing import Any, cast

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

# Redis retention bounds (#1529): every key this module writes either carries
# a TTL or is rank-trimmed, so a busy coordinator cannot grow the keyspace
# without limit. Message records and their per-agent index entries share one
# TTL; subscriptions and peer connections get longer windows because they
# are re-written on (re)connect/subscribe, which slides the expiry forward.
MESSAGE_TTL_SECONDS = 7 * 24 * 60 * 60
SUBSCRIPTION_TTL_SECONDS = 30 * 24 * 60 * 60
PEER_TTL_SECONDS = 24 * 60 * 60
# Per-agent index sets become zsets scored by message timestamp so reads can
# paginate with ZREVRANGE instead of SMEMBERS + fetch-all (#1529). The rank
# trim keeps only the newest entries per agent.
MAX_INDEXED_MESSAGES_PER_AGENT = 1_000
# Global timestamp zset bound — keeps the newest entries only.
MAX_TIMESTAMP_INDEX_ENTRIES = 100_000


class MessageStorage:
    """Redis-based message storage with a SQLite fallback."""

    def __init__(self, redis_url: str, database_url: str | None = None) -> None:
        """Initialize message storage with Redis and optional SQLite fallback."""
        import redis.asyncio as redis

        self.redis_url = redis_url
        self.redis: redis.Redis | None = None
        self.database_url = database_url
        self.sqlite_conn: Any | None = None
        self.sqlite_db_path: str | None = None

        if database_url and database_url.startswith("sqlite:///"):
            self.sqlite_db_path = database_url[len("sqlite:///") :]

    async def start(self) -> None:
        """Connect to Redis and prepare the SQLite fallback."""
        import redis.asyncio as redis

        try:
            self.redis = await redis.from_url(self.redis_url, decode_responses=True)
            logger.info("Message storage connected to Redis")
        except Exception as e:
            logger.error("Could not connect to Redis: %s", e)
            self.redis = None

        if self.sqlite_db_path:
            try:
                import aiosqlite

                db_dir = os.path.dirname(self.sqlite_db_path) or "."
                os.makedirs(db_dir, exist_ok=True)
                self.sqlite_conn = await aiosqlite.connect(self.sqlite_db_path)
                await self.sqlite_conn.execute(
                    "CREATE TABLE IF NOT EXISTS messages ("
                    "message_id TEXT PRIMARY KEY, "
                    "data TEXT NOT NULL, "
                    "sender TEXT, "
                    "receiver TEXT, "
                    "timestamp REAL, "
                    "status TEXT DEFAULT 'pending')"
                )
                await self.sqlite_conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender)")
                await self.sqlite_conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver)")
                await self.sqlite_conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)")
                await self.sqlite_conn.commit()
                logger.info("SQLite fallback initialised at %s", self.sqlite_db_path)
            except Exception as e:
                logger.error("Could not initialise SQLite fallback: %s", e)
                self.sqlite_conn = None

    async def stop(self) -> None:
        """Close Redis and SQLite connections."""
        if self.redis:
            await self.redis.aclose()
            logger.info("Message storage disconnected from Redis")
        if self.sqlite_conn:
            try:
                await self.sqlite_conn.close()
                logger.info("Message storage SQLite connection closed")
            except Exception as e:
                logger.error("Error closing SQLite fallback: %s", e)

    def _extract_sender(self, message_data: dict[str, Any]) -> str | None:
        return message_data.get("sender") or message_data.get("sender_id")

    def _extract_receiver(self, message_data: dict[str, Any]) -> str | None:
        return message_data.get("recipient") or message_data.get("receiver_id")

    def _timestamp_to_float(self, message_data: dict[str, Any]) -> float:
        timestamp_str = message_data.get("timestamp", datetime.now(UTC).isoformat())
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            try:
                return float(timestamp_str)
            except Exception:
                return datetime.now(UTC).timestamp()

    # ------------------------------------------------------------------
    # SQLite fallback helpers
    # ------------------------------------------------------------------

    async def _sqlite_purge_expired(self) -> None:
        """Delete fallback rows past ``MESSAGE_TTL_SECONDS`` (#1554).

        The Redis path expires message hashes after 7 days; the SQLite
        fallback had no equivalent, so rows accumulated forever whenever
        Redis was unavailable. Runs on the store path — one indexed DELETE
        per write keeps the table bounded without a separate sweeper.
        """
        if not self.sqlite_conn:
            return
        try:
            await self.sqlite_conn.execute("DELETE FROM messages WHERE timestamp < ?", (time.time() - MESSAGE_TTL_SECONDS,))
            await self.sqlite_conn.commit()
        except Exception as e:
            logger.error("SQLite expiry purge failed: %s", e)

    async def _sqlite_store(self, message_id: str, message_data: dict[str, Any]) -> bool:
        if not self.sqlite_conn:
            return False
        await self._sqlite_purge_expired()
        try:
            data = json.dumps(message_data)
            sender = self._extract_sender(message_data)
            receiver = self._extract_receiver(message_data)
            ts = self._timestamp_to_float(message_data)
            status = message_data.get("status", "pending")
            await self.sqlite_conn.execute(
                "INSERT OR REPLACE INTO messages (message_id, data, sender, receiver, timestamp, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (message_id, data, sender, receiver, ts, status),
            )
            await self.sqlite_conn.commit()
            logger.debug("Stored message %s in SQLite", message_id)
            return True
        except Exception as e:
            logger.error("SQLite store failed for %s: %s", message_id, e)
            return False

    async def _sqlite_get(self, message_id: str) -> dict[str, Any] | None:
        if not self.sqlite_conn:
            return None
        try:
            cursor = await self.sqlite_conn.execute("SELECT data FROM messages WHERE message_id = ?", (message_id,))
            row = await cursor.fetchone()
            if row:
                data: dict[str, Any] = json.loads(row[0])
                if "payload" in data:
                    data["payload"] = json.loads(data["payload"])
                return data
            return None
        except Exception as e:
            logger.error("SQLite get failed for %s: %s", message_id, e)
            return None

    async def _sqlite_update_status(self, message_id: str, status: str) -> bool:
        if not self.sqlite_conn:
            return False
        try:
            cursor = await self.sqlite_conn.execute("SELECT data FROM messages WHERE message_id = ?", (message_id,))
            row = await cursor.fetchone()
            if row:
                data = json.loads(row[0])
                data["status"] = status
                await self.sqlite_conn.execute(
                    "UPDATE messages SET data = ?, status = ? WHERE message_id = ?",
                    (json.dumps(data), status, message_id),
                )
            else:
                await self.sqlite_conn.execute(
                    "INSERT INTO messages (message_id, data, status) VALUES (?, ?, ?)",
                    (message_id, json.dumps({"status": status}), status),
                )
            await self.sqlite_conn.commit()
            return True
        except Exception as e:
            logger.error("SQLite update status failed for %s: %s", message_id, e)
            return False

    async def _sqlite_get_by_field(self, field: str, value: str, limit: int, offset: int) -> list[dict[str, Any]]:
        if not self.sqlite_conn:
            return []
        if field not in {"sender", "receiver"}:
            raise ValueError(f"invalid message query field: {field}")
        try:
            cursor = await self.sqlite_conn.execute(
                f"SELECT data FROM messages WHERE {field} = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",  # nosec
                (value, limit, offset),
            )
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                data = json.loads(row[0])
                if "payload" in data:
                    data["payload"] = json.loads(data["payload"])
                messages.append(data)
            return messages
        except Exception as e:
            logger.error("SQLite query failed for %s=%s: %s", field, value, e)
            return []

    async def _sqlite_get_all(self, limit: int, offset: int) -> list[dict[str, Any]]:
        if not self.sqlite_conn:
            return []
        try:
            cursor = await self.sqlite_conn.execute(
                "SELECT data FROM messages ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                data = json.loads(row[0])
                if "payload" in data:
                    data["payload"] = json.loads(data["payload"])
                messages.append(data)
            return messages
        except Exception as e:
            logger.error("SQLite get_all failed: %s", e)
            return []

    async def _sqlite_count(self) -> int:
        if not self.sqlite_conn:
            return 0
        try:
            cursor = await self.sqlite_conn.execute("SELECT COUNT(*) FROM messages")
            row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error("SQLite count failed: %s", e)
            return 0

    async def _sqlite_delete(self, message_id: str) -> bool:
        if not self.sqlite_conn:
            return False
        try:
            await self.sqlite_conn.execute("DELETE FROM messages WHERE message_id = ?", (message_id,))
            await self.sqlite_conn.commit()
            return True
        except Exception as e:
            logger.error("SQLite delete failed for %s: %s", message_id, e)
            return False

    async def _trim_index(self, key: str, keep: int = MAX_INDEXED_MESSAGES_PER_AGENT) -> None:
        """Keep only the newest ``keep`` members of a message index zset.

        Indexes are scored by message timestamp (epoch), so the oldest
        entries sit at the lowest ranks; ``zremrangebyrank`` drops them.
        """
        await self.redis.zremrangebyrank(key, 0, -keep - 1)  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store_message(self, message_id: str, message_data: dict[str, Any]) -> bool:
        """Store a message, preferring Redis and falling back to SQLite."""
        stored_in_redis = False
        if self.redis:
            try:
                message_key = f"message:{message_id}"
                await self.redis.hset(message_key, mapping=message_data)  # type: ignore[arg-type]
                await self.redis.expire(message_key, MESSAGE_TTL_SECONDS)
                ts = self._timestamp_to_float(message_data)
                sender_id = self._extract_sender(message_data)
                if sender_id:
                    sender_key = f"messages:sender:{sender_id}"
                    await self.redis.zadd(sender_key, {message_id: ts})
                    await self._trim_index(sender_key)
                receiver_id = self._extract_receiver(message_data)
                if receiver_id:
                    receiver_key = f"messages:receiver:{receiver_id}"
                    await self.redis.zadd(receiver_key, {message_id: ts})
                    await self._trim_index(receiver_key)
                await self.redis.zadd("messages:timestamp", {message_id: ts})
                await self._trim_index("messages:timestamp", MAX_TIMESTAMP_INDEX_ENTRIES)
                logger.debug("Stored message %s in Redis", message_id)
                stored_in_redis = True
            except Exception as e:
                logger.error("Redis store failed for %s: %s", message_id, e)

        if not stored_in_redis:
            return await self._sqlite_store(message_id, message_data)
        return True

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        """Retrieve a specific message by ID from Redis or SQLite."""
        if self.redis:
            try:
                message_data: dict[str, Any] = await self.redis.hgetall(f"message:{message_id}")  # type: ignore[assignment]
                if message_data:
                    if "payload" in message_data:
                        message_data["payload"] = json.loads(message_data["payload"])
                    return message_data
            except Exception as e:
                logger.error("Redis get failed for %s: %s", message_id, e)
        return await self._sqlite_get(message_id)

    async def update_message_status(self, message_id: str, status: str) -> bool:
        """Update the delivery status of a message."""
        redis_ok = False
        if self.redis:
            try:
                message_key = f"message:{message_id}"
                await self.redis.hset(message_key, "status", status)
                # hset on an expired/missing key recreates the hash without a
                # TTL — re-apply it so status writes cannot leak keys (#1529).
                await self.redis.expire(message_key, MESSAGE_TTL_SECONDS)
                redis_ok = True
            except Exception as e:
                logger.error("Redis update status failed for %s: %s", message_id, e)
        sqlite_ok = await self._sqlite_update_status(message_id, status)
        return redis_ok or sqlite_ok

    async def get_message_count(self) -> int:
        """Get total count of messages."""
        if self.redis:
            try:
                return await self.redis.zcard("messages:timestamp")
            except Exception as e:
                logger.error("Redis count failed: %s", e)
        return await self._sqlite_count()

    async def _messages_for_index(self, index_key: str, limit: int, offset: int) -> list[dict[str, Any]]:
        """Paginate a per-agent message index zset (newest first).

        Replaces the old SMEMBERS + fetch-all + Python-sort path: the zset
        score is the message timestamp, so ZREVRANGE gives the same ordering
        with true limit/offset pagination (#1529). Index entries whose
        message hash already expired are pruned lazily.
        """
        if self.redis is None:
            return []
        message_ids_raw = await self.redis.zrevrange(index_key, offset, offset + limit - 1)
        messages = []
        for mid in message_ids_raw:
            message_id = str(mid)
            data = await self.get_message(message_id)
            if data:
                messages.append(data)
            else:
                await self.redis.zrem(index_key, message_id)
        return messages

    async def get_messages_by_sender(self, sender_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get messages sent by a specific agent."""
        if self.redis:
            try:
                return await self._messages_for_index(f"messages:sender:{sender_id}", limit, offset)
            except Exception as e:
                logger.error("Redis get by sender failed for %s: %s", sender_id, e)
        return await self._sqlite_get_by_field("sender", sender_id, limit, offset)

    async def get_messages_by_receiver(self, receiver_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get messages received by a specific agent."""
        if self.redis:
            try:
                return await self._messages_for_index(f"messages:receiver:{receiver_id}", limit, offset)
            except Exception as e:
                logger.error("Redis get by receiver failed for %s: %s", receiver_id, e)
        return await self._sqlite_get_by_field("receiver", receiver_id, limit, offset)

    async def get_all_messages(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get all messages with pagination."""
        if self.redis:
            try:
                message_ids_raw = await self.redis.zrevrange("messages:timestamp", offset, offset + limit - 1)
                message_ids: list[str] = [str(m) for m in message_ids_raw]
                messages = []
                for message_id in message_ids:
                    message_data = await self.get_message(message_id)
                    if message_data:
                        messages.append(message_data)
                return messages
            except Exception as e:
                logger.error("Redis get all failed: %s", e)
        return await self._sqlite_get_all(limit, offset)

    async def delete_message(self, message_id: str) -> bool:
        """Delete a specific message."""
        message_data = await self.get_message(message_id)
        if not message_data:
            return False
        sender_id = self._extract_sender(message_data)
        receiver_id = self._extract_receiver(message_data)

        if self.redis:
            try:
                if sender_id:
                    await self.redis.zrem(f"messages:sender:{sender_id}", message_id)
                if receiver_id:
                    await self.redis.zrem(f"messages:receiver:{receiver_id}", message_id)
                await self.redis.zrem("messages:timestamp", message_id)
                await self.redis.delete(f"message:{message_id}")
                logger.debug("Deleted message %s from Redis", message_id)
            except Exception as e:
                logger.error("Redis delete failed for %s: %s", message_id, e)

        return await self._sqlite_delete(message_id)

    # ------------------------------------------------------------------
    # Topic subscriptions (Redis only for now)
    # ------------------------------------------------------------------

    async def add_subscription(self, agent_id: str, topic: str, filter: dict[str, Any] | None = None) -> bool:
        """Persist a topic subscription for an agent."""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        try:
            await self.redis.hset(
                f"subscription:{agent_id}:{topic}",
                mapping={
                    "agent_id": agent_id,
                    "topic": topic,
                    "filter": json.dumps(filter or {}),
                    "subscribed_at": datetime.now(UTC).isoformat(),
                },
            )
            await self.redis.expire(f"subscription:{agent_id}:{topic}", SUBSCRIPTION_TTL_SECONDS)
            await self.redis.sadd(f"subscriptions:agent:{agent_id}", topic)
            await self.redis.expire(f"subscriptions:agent:{agent_id}", SUBSCRIPTION_TTL_SECONDS)
            await self.redis.sadd(f"subscriptions:topic:{topic}", agent_id)
            await self.redis.expire(f"subscriptions:topic:{topic}", SUBSCRIPTION_TTL_SECONDS)
            logger.debug("Stored subscription %s:%s", agent_id, topic)
            return True
        except Exception as e:
            logger.error("Error storing subscription %s:%s: %s", agent_id, topic, e)
            return False

    async def remove_subscription(self, agent_id: str, topic: str) -> bool:
        """Remove a topic subscription for an agent."""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        try:
            await self.redis.srem(f"subscriptions:agent:{agent_id}", topic)
            await self.redis.srem(f"subscriptions:topic:{topic}", agent_id)
            await self.redis.delete(f"subscription:{agent_id}:{topic}")
            logger.debug("Removed subscription %s:%s", agent_id, topic)
            return True
        except Exception as e:
            logger.error("Error removing subscription %s:%s: %s", agent_id, topic, e)
            return False

    async def get_subscriptions(self, agent_id: str) -> list[dict[str, Any]]:
        """Get all persisted topic subscriptions for an agent."""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        try:
            # This client connects with decode_responses=True (see connect()), so
            # redis-py returns str; its stubs describe the undecoded bytes shape.
            topics = cast("set[str]", await self.redis.smembers(f"subscriptions:agent:{agent_id}"))
            # Slide the TTL forward on read so live subscriptions outlive the
            # retention window while abandoned ones expire (#1529).
            await self.redis.expire(f"subscriptions:agent:{agent_id}", SUBSCRIPTION_TTL_SECONDS)
            subscriptions = []
            for topic in topics:
                sub = cast("dict[str, Any]", await self.redis.hgetall(f"subscription:{agent_id}:{topic}"))
                if sub:
                    if "filter" in sub:
                        sub["filter"] = json.loads(sub["filter"])
                    subscriptions.append(sub)
            return subscriptions
        except Exception as e:
            logger.error("Error retrieving subscriptions for %s: %s", agent_id, e)
            return []

    async def get_topic_subscribers(self, topic: str) -> list[str]:
        """Get all agents subscribed to a topic."""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        try:
            raw = await self.redis.smembers(f"subscriptions:topic:{topic}")
            await self.redis.expire(f"subscriptions:topic:{topic}", SUBSCRIPTION_TTL_SECONDS)
            return [str(m) for m in raw]
        except Exception as e:
            logger.error("Error retrieving subscribers for topic %s: %s", topic, e)
            return []


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
        logger.info("Peer storage connected to Redis")

    async def stop(self) -> None:
        """Close Redis connection"""
        if self.redis:
            await self.redis.aclose()
            logger.info("Peer storage disconnected from Redis")

    async def add_peer(self, agent_id: str, peer_id: str, metadata: dict[str, Any] | None = None) -> bool:
        """Add a peer connection for an agent"""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        try:
            await self.redis.sadd(f"peers:{agent_id}", peer_id)
            await self.redis.expire(f"peers:{agent_id}", PEER_TTL_SECONDS)
            if metadata:
                peer_key = f"peer_connection:{agent_id}:{peer_id}"
                await self.redis.hset(peer_key, mapping=metadata)  # type: ignore[arg-type]
                await self.redis.expire(peer_key, PEER_TTL_SECONDS)
            logger.debug("Added peer %s for agent %s", peer_id, agent_id)
            return True
        except Exception as e:
            logger.error("Error adding peer %s for agent %s: %s", peer_id, agent_id, e)
            return False

    async def remove_peer(self, agent_id: str, peer_id: str) -> bool:
        """Remove a peer connection for an agent"""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        try:
            await self.redis.srem(f"peers:{agent_id}", peer_id)
            await self.redis.delete(f"peer_connection:{agent_id}:{peer_id}")
            logger.debug("Removed peer %s for agent %s", peer_id, agent_id)
            return True
        except Exception as e:
            logger.error("Error removing peer %s for agent %s: %s", peer_id, agent_id, e)
            return False

    async def get_agent_peers(self, agent_id: str) -> list[str]:
        """Get all peers for a specific agent"""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        try:
            peers_key = f"peers:{agent_id}"
            peer_ids_raw = await self.redis.smembers(peers_key)
            await self.redis.expire(peers_key, PEER_TTL_SECONDS)
            return [str(m) for m in peer_ids_raw]
        except Exception as e:
            logger.error("Error retrieving peers for agent %s: %s", agent_id, e)
            return []

    async def get_peer_metadata(self, agent_id: str, peer_id: str) -> dict[str, Any] | None:
        """Get metadata for a specific peer connection"""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        try:
            peer_key = f"peer_connection:{agent_id}:{peer_id}"
            metadata_raw: dict[str, Any] = await self.redis.hgetall(peer_key)  # type: ignore[assignment]
            if metadata_raw:
                await self.redis.expire(peer_key, PEER_TTL_SECONDS)
            return metadata_raw if metadata_raw else None
        except Exception as e:
            logger.error("Error retrieving peer metadata for %s:%s: %s", agent_id, peer_id, e)
            return None

    async def get_all_peer_connections(self) -> dict[str, list[str]]:
        """Get all peer connections in the system"""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        try:
            # scan_iter keeps this off the O(keyspace) KEYS path (#1530);
            # batches are bounded by the SCAN COUNT hint.
            peer_keys = [key async for key in self.redis.scan_iter("peers:*")]
            connections = {}
            for key in peer_keys:
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                agent_id = key_str.replace("peers:", "")
                peer_ids = await self.redis.smembers(key)
                peer_list: list[str] = [pid.decode("utf-8") if isinstance(pid, bytes) else str(pid) for pid in peer_ids]
                connections[agent_id] = peer_list
            return connections
        except Exception as e:
            logger.error("Error retrieving all peer connections: %s", e)
            return {}
