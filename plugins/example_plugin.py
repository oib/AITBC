"""
AITBC Plugin Development Starter Kit

This template provides a complete starting point for developing AITBC plugins.
Follow the PLUGIN_SPEC.md for detailed interface requirements.
"""

from aitbc.plugins import BasePlugin, PluginMetadata, PluginContext
from typing import Dict, Any, List
import asyncio
import logging


class ExamplePlugin(BasePlugin):
    """Example plugin demonstrating the AITBC plugin interface."""
    
    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="example-plugin",
            version="1.0.0",
            description="Example plugin for AITBC platform",
            author="Your Name",
            license="MIT",
            homepage="https://github.com/yourusername/example-plugin",
            repository="https://github.com/yourusername/example-plugin",
            keywords=["example", "aitbc", "plugin"],
            dependencies=[],
            min_aitbc_version="1.0.0",
            max_aitbc_version="2.0.0",
            supported_platforms=["linux", "macos", "windows"]
        )
    
    async def initialize(self) -> bool:
        """Initialize the plugin."""
        try:
            self.context.logger.info("Initializing example plugin")
            
            # Load plugin configuration
            self.config = self.context.config.get("example-plugin", {})
            
            # Initialize plugin state
            self._start_time = None
            self._error_count = 0
            self._memory_usage = 0
            
            # Setup any required resources
            await self._setup_resources()
            
            self.context.logger.info("Example plugin initialized successfully")
            return True
            
        except Exception as e:
            self.context.logger.error(f"Failed to initialize example plugin: {e}")
            self._error_count += 1
            return False
    
    async def start(self) -> bool:
        """Start the plugin."""
        try:
            self.context.logger.info("Starting example plugin")
            
            # Start plugin services
            await self._start_services()
            
            # Record start time
            import time
            self._start_time = time.time()
            
            self.status = PluginStatus.ACTIVE
            self.context.logger.info("Example plugin started successfully")
            return True
            
        except Exception as e:
            self.context.logger.error(f"Failed to start example plugin: {e}")
            self._error_count += 1
            return False
    
    async def stop(self) -> bool:
        """Stop the plugin."""
        try:
            self.context.logger.info("Stopping example plugin")
            
            # Stop plugin services
            await self._stop_services()
            
            self.status = PluginStatus.INACTIVE
            self.context.logger.info("Example plugin stopped successfully")
            return True
            
        except Exception as e:
            self.context.logger.error(f"Failed to stop example plugin: {e}")
            self._error_count += 1
            return False
    
    async def cleanup(self) -> bool:
        """Cleanup plugin resources."""
        try:
            self.context.logger.info("Cleaning up example plugin")
            
            # Cleanup resources
            await self._cleanup_resources()
            
            self.status = PluginStatus.UNLOADED
            self.context.logger.info("Example plugin cleaned up successfully")
            return True
            
        except Exception as e:
            self.context.logger.error(f"Failed to cleanup example plugin: {e}")
            self._error_count += 1
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Return plugin health status."""
        import time
        import psutil
        import os
        
        # Calculate memory usage
        try:
            process = psutil.Process(os.getpid())
            self._memory_usage = process.memory_info().rss
        except:
            self._memory_usage = 0
        
        uptime = None
        if self._start_time:
            uptime = time.time() - self._start_time
        
        return {
            "status": self.status.value,
            "uptime": uptime,
            "memory_usage": self._memory_usage,
            "error_count": self._error_count,
            "version": self.get_metadata().version,
            "last_check": time.time()
        }
    
    async def handle_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle system events."""
        self.context.logger.debug(f"Handling event: {event_type}")
        
        if event_type == "user_login":
            await self._handle_user_login(data)
        elif event_type == "transaction_completed":
            await self._handle_transaction_completed(data)
        elif event_type == "system_shutdown":
            await self._handle_system_shutdown(data)
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Return configuration schema."""
        return {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable the plugin"
                },
                "log_level": {
                    "type": "string",
                    "enum": ["DEBUG", "INFO", "WARNING", "ERROR"],
                    "default": "INFO",
                    "description": "Log level for the plugin"
                },
                "max_connections": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 10,
                    "description": "Maximum number of connections"
                },
                "api_endpoint": {
                    "type": "string",
                    "format": "uri",
                    "description": "API endpoint URL"
                }
            },
            "required": ["enabled"]
        }
    
    # Private helper methods
    async def _setup_resources(self) -> None:
        """Setup plugin resources."""
        # Example: Setup database connections, API clients, etc.
        pass
    
    async def _start_services(self) -> None:
        """Start plugin services."""
        # Example: Start background tasks, web servers, etc.
        pass
    
    async def _stop_services(self) -> None:
        """Stop plugin services."""
        # Example: Stop background tasks, web servers, etc.
        pass
    
    async def _cleanup_resources(self) -> None:
        """Cleanup plugin resources."""
        # Example: Close database connections, cleanup files, etc.
        pass
    
    async def _handle_user_login(self, data: Dict[str, Any]) -> None:
        """Handle user login events."""
        user_id = data.get("user_id")
        self.context.logger.info(f"User {user_id} logged in")
    
    async def _handle_transaction_completed(self, data: Dict[str, Any]) -> None:
        """Handle transaction completed events."""
        tx_hash = data.get("transaction_hash")
        amount = data.get("amount")
        self.context.logger.info(f"Transaction {tx_hash} completed with amount {amount}")
    
    async def _handle_system_shutdown(self, data: Dict[str, Any]) -> None:
        """Handle system shutdown events."""
        self.context.logger.info("System shutting down, preparing plugin for shutdown")
        await self.stop()


# Plugin factory function
def create_plugin(context: PluginContext) -> BasePlugin:
    """Create and return plugin instance."""
    return ExamplePlugin(context)


# Plugin entry point
def get_plugin_info() -> Dict[str, Any]:
    """Return plugin information for registry."""
    return {
        "name": "example-plugin",
        "version": "1.0.0",
        "description": "Example plugin for AITBC platform",
        "author": "Your Name",
        "license": "MIT",
        "homepage": "https://github.com/yourusername/example-plugin",
        "repository": "https://github.com/yourusername/example-plugin",
        "keywords": ["example", "aitbc", "plugin"],
        "dependencies": [],
        "min_aitbc_version": "1.0.0",
        "max_aitbc_version": "2.0.0",
        "supported_platforms": ["linux", "macos", "windows"],
        "entry_point": "create_plugin",
        "config_schema": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": True},
                "log_level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR"], "default": "INFO"},
                "max_connections": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}
            },
            "required": ["enabled"]
        }
    }


# Example CLI plugin (optional)
try:
    from aitbc.plugins import CLIPlugin
    from click import Group
    
    class ExampleCLIPlugin(CLIPlugin, ExamplePlugin):
        """Example CLI plugin extending the base plugin."""
        
        def get_commands(self) -> List[Group]:
            """Return CLI command groups."""
            @click.group()
            def example():
                """Example plugin commands"""
                pass
            
            @example.command()
            @click.option('--count', default=1, help='Number of greetings')
            @click.argument('name')
            def greet(count, name):
                """Greet someone multiple times"""
                for _ in range(count):
                    click.echo(f"Hello {name}!")
            
            @example.command()
            def status():
                """Get plugin status"""
                click.echo("Example plugin is running")
            
            return [example]
        
        def get_command_help(self) -> str:
            """Return help text for commands."""
            return """
Example Plugin Commands:
  greet    Greet someone multiple times
  status   Get plugin status
            """
    
    def create_cli_plugin(context: PluginContext) -> CLIPlugin:
        """Create and return CLI plugin instance."""
        return ExampleCLIPlugin(context)
        
except ImportError:
    # CLI plugin interface not available
    pass


# Example Blockchain plugin (optional)
try:
    from aitbc.plugins import BlockchainPlugin
    
    class ExampleBlockchainPlugin(BlockchainPlugin, ExamplePlugin):
        """Example blockchain plugin extending the base plugin."""
        
        async def connect(self, config: Dict[str, Any]) -> bool:
            """Connect to blockchain network."""
            self.context.logger.info("Connecting to blockchain network")
            # Implement blockchain connection logic
            return True
        
        async def get_balance(self, address: str) -> Dict[str, Any]:
            """Get account balance."""
            # Implement balance retrieval logic
            return {"address": address, "balance": "0", "currency": "ETH"}
        
        async def send_transaction(self, tx_data: Dict[str, Any]) -> str:
            """Send transaction and return hash."""
            # Implement transaction sending logic
            return "0x1234567890abcdef"
        
        async def get_contract_events(self, contract_address: str, 
                                     event_name: str, 
                                     from_block: int = None) -> List[Dict[str, Any]]:
            """Get contract events."""
            # Implement event retrieval logic
            return []
    
    def create_blockchain_plugin(context: PluginContext) -> BlockchainPlugin:
        """Create and return blockchain plugin instance."""
        return ExampleBlockchainPlugin(context)
        
except ImportError:
    # Blockchain plugin interface not available
    pass


# Example AI plugin (optional)
try:
    from aitbc.plugins import AIPlugin
    
    class ExampleAIPlugin(AIPlugin, ExamplePlugin):
        """Example AI plugin extending the base plugin."""
        
        async def predict(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
            """Make prediction using AI model."""
            # Implement prediction logic
            return {"prediction": "example", "confidence": 0.95}
        
        async def train(self, training_data: List[Dict[str, Any]]) -> bool:
            """Train AI model."""
            # Implement training logic
            return True
        
        def get_model_info(self) -> Dict[str, Any]:
            """Get model information."""
            return {
                "model_type": "example",
                "version": "1.0.0",
                "accuracy": 0.95,
                "trained_on": "2024-01-01"
            }
    
    def create_ai_plugin(context: PluginContext) -> AIPlugin:
        """Create and return AI plugin instance."""
        return ExampleAIPlugin(context)
        
except ImportError:
    # AI plugin interface not available
    pass


if __name__ == "__main__":
    # Plugin can be tested independently
    import asyncio
    
    async def test_plugin():
        """Test the plugin."""
        from aitbc.plugins import PluginContext
        
        # Create test context
        context = PluginContext(
            config={"example-plugin": {"enabled": True}},
            data_dir="/tmp/aitbc",
            temp_dir="/tmp/aitbc/tmp",
            logger=logging.getLogger("example-plugin"),
            event_bus=None,
            api_client=None
        )
        
        # Create plugin
        plugin = create_plugin(context)
        
        # Test plugin lifecycle
        assert await plugin.initialize() is True
        assert await plugin.start() is True
        
        # Test health check
        health = await plugin.health_check()
        assert health["status"] == "active"
        
        # Test event handling
        await plugin.handle_event("test_event", {"data": "test"})
        
        # Cleanup
        assert await plugin.stop() is True
        assert await plugin.cleanup() is True
        
        print("Plugin test completed successfully!")
    
    asyncio.run(test_plugin())
