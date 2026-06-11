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
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    async def send_message(self, recipient: str, content: str):
        """Send a message via WebSocket"""
        message = {
            "type": "message",
            "payload": {
                "recipient_id": recipient,
                "content": content
            }
        }
        
        # This would be sent through the active WebSocket connection
        # For now, we'll implement it as a separate function
        self.logger.info(f"Message prepared for {recipient}: {content}")
        return True

    async def connect_and_listen(self):
        """Connect to WebSocket and listen for messages"""
        uri = f"{self.ws_url}/api/v1/agent/messages/stream?agent_id={self.agent_id}"
        
        self.logger.info(f"Connecting to WebSocket: {uri}")
        
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    self.logger.info(f"WebSocket connected for agent: {self.agent_id}")
                    
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
                            self.logger.error(f"Error receiving message: {e}")
                            break
                            
            except Exception as e:
                self.logger.error(f"WebSocket connection error: {e}")
                if self.running:
                    self.logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def handle_message(self, data: dict):
        """Handle incoming WebSocket message"""
        message_type = data.get("type", "unknown")
        
        if message_type == "connection_established":
            self.logger.info(f"WebSocket connection established: {data.get('message')}")
            
        elif message_type == "PONG":
            self.logger.info(f"Received PONG: {data.get('content')}")
            
        elif message_type == "handler_acknowledgment":
            self.logger.info(f"Handler triggered: {data.get('handler_results')}")
            
        elif message_type == "message":
            sender = data.get("sender_id", "unknown")
            content = data.get("content", "")
            self.logger.info(f"Received message from {sender}: {content}")
            
        else:
            self.logger.info(f"Received message type: {message_type}")

    def run(self):
        """Main WebSocket loop"""
        self.logger.info(f"Hermes WebSocket daemon started for agent: {self.agent_id}")
        self.logger.info(f"WebSocket URL: {self.ws_url}/api/v1/agent/messages/stream")
        
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
        help=f"Agent Coordinator endpoint (default: {DEFAULT_COORDINATOR_URL})"
    )
    parser.add_argument(
        "--agent-id",
        required=True,
        help="Agent ID for WebSocket connection"
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Logging level (default: {DEFAULT_LOG_LEVEL})"
    )

    args = parser.parse_args()

    # Create and run daemon
    daemon = HermesWebSocketDaemon(
        coordinator_url=args.coordinator_url,
        agent_id=args.agent_id,
        log_level=args.log_level
    )

    daemon.run()


if __name__ == "__main__":
    main()
