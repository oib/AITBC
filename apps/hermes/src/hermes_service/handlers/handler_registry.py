"""Handler registry for managing message handlers."""

import importlib
import logging
import pkgutil
from typing import Any

from .base_handler import BaseHandler


class HandlerRegistry:
    """Registry for managing and loading message handlers."""

    def __init__(self, coordinator_url: str, agent_id: str):
        self.coordinator_url = coordinator_url
        self.agent_id = agent_id
        self.handlers: list[BaseHandler] = []
        self.logger = logging.getLogger(__name__)

    def register_handler(self, handler: BaseHandler):
        """Register a handler instance."""
        self.handlers.append(handler)
        self.logger.info(f"Registered handler: {handler.__class__.__name__}")

    def load_handlers_from_module(self, module_name: str):
        """Dynamically load handlers from a module."""
        try:
            module = importlib.import_module(module_name)
            for name, obj in vars(module).items():
                if isinstance(obj, type) and issubclass(obj, BaseHandler) and obj != BaseHandler:
                    handler_instance = obj(self.coordinator_url, self.agent_id)
                    self.register_handler(handler_instance)
        except Exception as e:
            self.logger.error(f"Failed to load handlers from {module_name}: {e}")

    def load_all_handlers(self):
        """Load all handlers from the handlers package."""
        import hermes_service.handlers as handlers_package

        for importer, modname, ispkg in pkgutil.iter_modules(handlers_package.__path__):
            if modname != "base_handler" and modname != "handler_registry":
                try:
                    module = importlib.import_module(f"hermes_service.handlers.{modname}")
                    for name, obj in vars(module).items():
                        if isinstance(obj, type) and issubclass(obj, BaseHandler) and obj != BaseHandler:
                            handler_instance = obj(self.coordinator_url, self.agent_id)
                            self.register_handler(handler_instance)
                except Exception as e:
                    self.logger.error(f"Failed to load handler {modname}: {e}")

    async def process_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Process a message through registered handlers."""
        content = message.get("content", "")

        for handler in self.handlers:
            if handler.can_handle(content):
                self.logger.info(f"Processing message with {handler.__class__.__name__}")
                return await handler.handle(message)

        self.logger.info(f"No handler found for message: {content}")
        return {"status": "no_handler", "message_id": message.get("id")}
