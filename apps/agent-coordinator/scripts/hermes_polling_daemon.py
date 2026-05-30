#!/usr/bin/env python3
"""
AITBC Hermes Polling Daemon
Polls the Coordinator API for Hermes messages and processes them with configurable handlers.
"""

import sys
import time
import requests
import argparse
import logging
from typing import Dict, Set, Callable, Optional
from datetime import datetime

# Default configuration
DEFAULT_COORDINATOR_URL = "http://localhost:8011"
DEFAULT_POLL_INTERVAL = 2
DEFAULT_LOG_LEVEL = "INFO"


class HermesPollingDaemon:
    """Daemon for polling Hermes API and processing messages"""

    def __init__(
        self,
        coordinator_url: str,
        agent_id: str,
        poll_interval: int,
        log_level: str,
        hermes_service_url: str = "http://localhost:8014"
    ):
        self.coordinator_url = coordinator_url.rstrip("/")
        self.agent_id = agent_id
        self.poll_interval = poll_interval
        self.processed_messages: Set[str] = set()
        self.message_handlers: Dict[str, Callable] = {}
        self.hermes_service_url = hermes_service_url.rstrip("/")
        self.running = True

        # Setup logging
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register built-in message handlers"""
        # No automatic handlers - let Hermes handle all messages
        pass

    def register_handler(self, trigger: str, handler: Callable):
        """Register a custom message handler"""
        self.message_handlers[trigger] = handler
        self.logger.info(f"Registered handler for trigger: {trigger}")

    def send_message(self, sender: str, recipient: str, content: str):
        """Send a message via Hermes API"""
        url = f"{self.coordinator_url}/v1/hermes/messages/send"
        payload = {
            "sender": sender,
            "recipient": recipient,
            "content": content,
            "message_type": "direct"
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                self.logger.info(f"Message sent successfully: {response.json()}")
                return True
            else:
                self.logger.error(f"Failed to send message: {response.text}")
                return False
        except requests.RequestException as e:
            self.logger.error(f"Network error sending message: {e}")
            return False

    def poll_messages(self) -> list:
        """Poll Hermes API for messages"""
        url = f"{self.coordinator_url}/v1/hermes/messages/{self.agent_id}"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("messages", [])
            else:
                self.logger.error(f"Failed to poll messages: {response.text}")
                return []
        except requests.RequestException as e:
            self.logger.error(f"Network error polling messages: {e}")
            return []

    def process_message(self, message: dict):
        """Process a single message by forwarding to Hermes service"""
        content = message.get("content", "")
        sender = message.get("sender", "unknown")

        self.logger.info(f"Forwarding message from {sender} to Hermes service: {content}")

        # Forward message to Hermes service
        try:
            response = requests.post(
                f"{self.hermes_service_url}/message",
                json=message,
                timeout=10
            )
            if response.status_code == 200:
                self.logger.info(f"Message forwarded successfully to Hermes service")
            else:
                self.logger.error(f"Failed to forward message to Hermes service: {response.text}")
        except requests.RequestException as e:
            self.logger.error(f"Network error forwarding to Hermes service: {e}")

    def run(self):
        """Main polling loop"""
        self.logger.info(f"Hermes polling daemon started for agent: {self.agent_id}")
        self.logger.info(f"Polling {self.coordinator_url}/v1/hermes/messages/{self.agent_id}")
        self.logger.info(f"Poll interval: {self.poll_interval} seconds")

        while self.running:
            try:
                messages = self.poll_messages()

                for message in messages:
                    msg_id = message.get("id")
                    if msg_id and msg_id not in self.processed_messages:
                        self.processed_messages.add(msg_id)
                        self.process_message(message)

                # Clean up old processed message IDs to prevent memory bloat
                if len(self.processed_messages) > 10000:
                    # Keep only the most recent 5000
                    self.processed_messages = set(list(self.processed_messages)[-5000:])

                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                self.logger.info("Received interrupt signal, shutting down...")
                self.running = False
            except Exception as e:
                self.logger.error(f"Error in polling loop: {e}", exc_info=True)
                time.sleep(self.poll_interval)

        self.logger.info("Hermes polling daemon stopped")


def main():
    parser = argparse.ArgumentParser(description="AITBC Hermes Polling Daemon")
    parser.add_argument(
        "--coordinator-url",
        default=DEFAULT_COORDINATOR_URL,
        help=f"Coordinator API endpoint (default: {DEFAULT_COORDINATOR_URL})"
    )
    parser.add_argument(
        "--agent-id",
        required=True,
        help="Agent ID to poll messages for"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        help=f"Polling interval in seconds (default: {DEFAULT_POLL_INTERVAL})"
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Logging level (default: {DEFAULT_LOG_LEVEL})"
    )
    parser.add_argument(
        "--hermes-service-url",
        default="http://localhost:8014",
        help="Hermes service URL for message forwarding (default: http://localhost:8014)"
    )

    args = parser.parse_args()

    # Create and run daemon
    daemon = HermesPollingDaemon(
        coordinator_url=args.coordinator_url,
        agent_id=args.agent_id,
        poll_interval=args.poll_interval,
        log_level=args.log_level,
        hermes_service_url=args.hermes_service_url
    )

    daemon.run()


if __name__ == "__main__":
    main()
