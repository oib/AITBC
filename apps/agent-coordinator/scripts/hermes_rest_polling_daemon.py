"""
AITBC Hermes REST Polling Daemon
Polls Agent Coordinator REST API for messages and forwards them to Hermes Service.
"""

import argparse
import asyncio
import hashlib
import logging
import os
from typing import Any

import httpx

DEFAULT_COORDINATOR_URL = "http://localhost:8107"
DEFAULT_HERMES_URL = "http://localhost:8103"
DEFAULT_POLL_INTERVAL = 60.0
DEFAULT_LOG_LEVEL = "INFO"


class HermesRestPollingDaemon:
    """Daemon that polls Agent Coordinator REST API and forwards messages to Hermes."""

    def __init__(self, coordinator_url: str, hermes_url: str, agent_id: str, poll_interval: float, log_level: str):
        self.coordinator_url = coordinator_url.rstrip("/")
        self.hermes_url = hermes_url.rstrip("/")
        self.agent_id = agent_id
        self.poll_interval = poll_interval
        self.running = True
        logging.basicConfig(level=getattr(logging, log_level.upper()), format="[%(levelname)s] %(message)s")
        self.logger = logging.getLogger("hermes-polling")
        self._seen_messages: set[str] = set()

    def _message_hash(self, message: dict[str, Any]) -> str:
        """Generate a deterministic hash for a message."""
        content = message.get("content", "")
        sender = message.get("sender", message.get("sender_id", ""))
        ts = message.get("timestamp", "")
        raw = f"{sender}:{content}:{ts}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    async def poll_messages(self) -> list[dict[str, Any]]:
        """Poll Agent Coordinator for messages addressed to this agent."""
        url = f"{self.coordinator_url}/api/v1/agent/messages/{self.agent_id}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                return data.get("messages", [])
        except httpx.HTTPStatusError as e:
            self.logger.warning("HTTP error polling messages: %s", e.response.status_code)
            return []
        except httpx.ConnectError as e:
            self.logger.warning("Connection error polling messages: %s", e)
            return []
        except Exception as e:
            self.logger.error("Unexpected error polling messages: %s", e)
            return []

    async def forward_to_hermes(self, message: dict[str, Any]) -> bool:
        """Forward a single message to the Hermes service."""
        url = f"{self.hermes_url}/message"
        payload = {
            "id": message.get("id", self._message_hash(message)),
            "sender": message.get("sender", message.get("sender_id", "unknown")),
            "recipient": message.get("recipient", message.get("receiver_id", self.agent_id)),
            "content": message.get("content", ""),
            "timestamp": message.get("timestamp", ""),
            "message_type": message.get("message_type", "direct"),
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                self.logger.info("Forwarded message %s from %s to Hermes", payload["id"], payload["sender"])
                return True
        except httpx.HTTPStatusError as e:
            self.logger.error("Hermes returned %s for message %s", e.response.status_code, payload["id"])
            return False
        except httpx.ConnectError as e:
            self.logger.error("Cannot connect to Hermes at %s: %s", self.hermes_url, e)
            return False
        except Exception as e:
            self.logger.error("Failed to forward message to Hermes: %s", e)
            return False

    async def run_once(self) -> int:
        """Perform one polling cycle. Returns number of messages forwarded."""
        messages = await self.poll_messages()
        forwarded = 0
        for message in messages:
            msg_hash = self._message_hash(message)
            if msg_hash in self._seen_messages:
                continue
            success = await self.forward_to_hermes(message)
            if success:
                self._seen_messages.add(msg_hash)
                forwarded += 1
        if len(self._seen_messages) > 10000:
            self._seen_messages = set(list(self._seen_messages)[-5000:])
        return forwarded

    async def run(self):
        """Main polling loop."""
        self.logger.info("Hermes REST polling daemon started for agent: %s", self.agent_id)
        self.logger.info("Coordinator URL: %s", self.coordinator_url)
        self.logger.info("Hermes URL: %s", self.hermes_url)
        self.logger.info("Poll interval: %ss", self.poll_interval)
        while self.running:
            try:
                forwarded = await self.run_once()
                if forwarded > 0:
                    self.logger.info("Forwarded %s message(s) in this cycle", forwarded)
            except Exception as e:
                self.logger.error("Error in polling cycle: %s", e)
            if self.running:
                await asyncio.sleep(self.poll_interval)
        self.logger.info("Hermes REST polling daemon stopped")


def main():
    parser = argparse.ArgumentParser(description="AITBC Hermes REST Polling Daemon")
    parser.add_argument(
        "--coordinator-url",
        default=os.getenv("HERMES_COORDINATOR_URL", DEFAULT_COORDINATOR_URL),
        help=f"Agent Coordinator endpoint (default: {DEFAULT_COORDINATOR_URL})",
    )
    parser.add_argument(
        "--hermes-url",
        default=os.getenv("HERMES_SERVICE_URL", DEFAULT_HERMES_URL),
        help=f"Hermes service endpoint (default: {DEFAULT_HERMES_URL})",
    )
    parser.add_argument("--agent-id", required=True, help="Agent ID to poll messages for")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("HERMES_POLL_INTERVAL", str(DEFAULT_POLL_INTERVAL))),
        help=f"Polling interval in seconds (default: {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Logging level (default: {DEFAULT_LOG_LEVEL})",
    )
    args = parser.parse_args()
    daemon = HermesRestPollingDaemon(
        coordinator_url=args.coordinator_url,
        hermes_url=args.hermes_url,
        agent_id=args.agent_id,
        poll_interval=args.poll_interval,
        log_level=args.log_level,
    )
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        daemon.logger.info("Received interrupt signal, shutting down...")
        daemon.running = False


if __name__ == "__main__":
    main()
