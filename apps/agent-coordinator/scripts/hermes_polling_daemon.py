#!/usr/bin/env python3
"""
AITBC Hermes WebSocket Daemon
Connects to Agent Coordinator WebSocket for real-time message processing with automatic handler triggering.
"""

import argparse
import asyncio
import json
import logging

import websockets

# Default configuration
DEFAULT_COORDINATOR_URL = "http://localhost:8107"
DEFAULT_WS_URL = "ws://localhost:8107"
DEFAULT_LOG_LEVEL = "INFO"


class HermesWebSocketDaemon:
    """Daemon for WebSocket connection to Agent Coordinator with automatic handler triggering"""

    def __init__(
        self,
        coordinator_url: str,
        agent_id: str,
        log_level: str,
    ):
        self.coordinator_url = coordinator_url.rstrip("/")
        self.agent_id = agent_id
        self.ws_url = coordinator_url.replace("http://", "ws://").replace("https://", "wss://")
        self.running = True

        # Setup logging
        logging.basicConfig(level=getattr(logging, log_level.upper()), format="[%(levelname)s] %(message)s")
        self.logger = logging.getLogger(__name__)

    async def send_message(self, recipient: str, content: str):
        """Send a message via WebSocket"""

        # This would be sent through the active WebSocket connection
        # For now, we'll implement it as a separate function
        self.logger.info("Message prepared for %s: %s", recipient, content)
        return True

    async def connect_and_listen(self):
        """Connect to WebSocket and listen for messages"""
        uri = f"{self.ws_url}/api/v1/agent/messages/stream?agent_id={self.agent_id}"

        self.logger.info("Connecting to WebSocket: %s", uri)

        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    self.logger.info("WebSocket connected for agent: %s", self.agent_id)

                    # Listen for messages
                    while self.running:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)
                            await self.handle_message(data)
                        except websockets.exceptions.ConnectionClosed:
                            self.logger.warning("WebSocket connection closed, reconnecting...")
                            break
                        except Exception as e:
                            self.logger.error("Error receiving message: %s", e)
                            break

            except Exception as e:
                self.logger.error("WebSocket connection error: %s", e)
                if self.running:
                    self.logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def handle_message(self, data: dict):
        """Handle incoming WebSocket message"""
        message_type = data.get("type", "unknown")

        if message_type == "connection_established":
            self.logger.info("WebSocket connection established: %s", data.get("message"))

        elif message_type == "PONG":
            self.logger.info("Received PONG: %s", data.get("content"))

        elif message_type == "handler_acknowledgment":
            self.logger.info("Handler triggered: %s", data.get("handler_results"))

        elif message_type == "message":
            sender = data.get("sender_id", "unknown")
            content = data.get("content", "")
            self.logger.info("Received message from %s: %s", sender, content)

        else:
            self.logger.info("Received message type: %s", message_type)

    def run(self):
        """Main WebSocket loop"""
        self.logger.info("Hermes WebSocket daemon started for agent: %s", self.agent_id)
        self.logger.info("WebSocket URL: %s/api/v1/agent/messages/stream", self.ws_url)

        try:
            asyncio.run(self.connect_and_listen())
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, shutting down...")
            self.running = False

        self.logger.info("Hermes WebSocket daemon stopped")


def main():
    parser = argparse.ArgumentParser(description="AITBC Hermes WebSocket Daemon")
    parser.add_argument(
        "--coordinator-url",
        default=DEFAULT_COORDINATOR_URL,
        help=f"Agent Coordinator endpoint (default: {DEFAULT_COORDINATOR_URL})",
    )
    parser.add_argument("--agent-id", required=True, help="Agent ID for WebSocket connection")
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Logging level (default: {DEFAULT_LOG_LEVEL})",
    )

    args = parser.parse_args()

    # Create and run daemon
    daemon = HermesWebSocketDaemon(coordinator_url=args.coordinator_url, agent_id=args.agent_id, log_level=args.log_level)

    daemon.run()


if __name__ == "__main__":
    main()
