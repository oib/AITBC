# AITBC Plugin Interface Specification

## Overview

The AITBC platform supports a plugin architecture that allows developers to extend functionality through well-defined interfaces. This specification defines the plugin interface, lifecycle, and integration patterns.

## Plugin Architecture

### Core Concepts

- **Plugin**: Self-contained module that extends AITBC functionality
- **Plugin Manager**: Central system for loading, managing, and coordinating plugins
- **Plugin Interface**: Contract that plugins must implement
- **Plugin Lifecycle**: States and transitions during plugin operation
- **Plugin Registry**: Central repository for plugin discovery and metadata

## Plugin Interface Definition

### Base Plugin Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

class PluginStatus(Enum):
    """Plugin operational states"""
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    UNLOADING = "unloading"

@dataclass
class PluginMetadata:
    """Plugin metadata structure"""
    name: str
    version: str
    description: str
    author: str
    license: str
    homepage: Optional[str] = None
    repository: Optional[str] = None
    keywords: List[str] = None
    dependencies: List[str] = None
    min_aitbc_version: str = None
    max_aitbc_version: str = None
    supported_platforms: List[str] = None

@dataclass
class PluginContext:
    """Runtime context provided to plugins"""
    config: Dict[str, Any]
    data_dir: str
    temp_dir: str
    logger: Any
    event_bus: Any
    api_client: Any

class BasePlugin(ABC):
    """Base interface that all plugins must implement"""
    
    def __init__(self, context: PluginContext):
        self.context = context
        self.status = PluginStatus.UNLOADED
        self.metadata = self.get_metadata()
    
    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata"""
        pass
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the plugin"""
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """Start the plugin"""
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """Stop the plugin"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> bool:
        """Cleanup plugin resources"""
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """Return plugin health status"""
        return {
            "status": self.status.value,
            "uptime": getattr(self, "_start_time", None),
            "memory_usage": getattr(self, "_memory_usage", 0),
            "error_count": getattr(self, "_error_count", 0)
        }
    
    async def handle_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Handle system events (optional)"""
        pass
    
    def get_config_schema(self) -> Dict[str, Any]:
        """Return configuration schema (optional)"""
        return {}
```

### Specialized Plugin Interfaces

#### CLI Plugin Interface

```python
from click import Group
from typing import List

class CLIPlugin(BasePlugin):
    """Interface for CLI command plugins"""
    
    @abstractmethod
    def get_commands(self) -> List[Group]:
        """Return CLI command groups"""
        pass
    
    @abstractmethod
    def get_command_help(self) -> str:
        """Return help text for commands"""
        pass

# Example CLI plugin
class AgentCLIPlugin(CLIPlugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="agent-cli",
            version="1.0.0",
            description="Agent management CLI commands",
            author="AITBC Team",
            license="MIT",
            keywords=["cli", "agent", "management"]
        )
    
    def get_commands(self) -> List[Group]:
        @click.group()
        def agent():
            """Agent management commands"""
            pass
        
        @agent.command()
        @click.option('--name', required=True, help='Agent name')
        def create(name):
            """Create a new agent"""
            click.echo(f"Creating agent: {name}")
        
        return [agent]
```

#### Blockchain Plugin Interface

```python
from web3 import Web3
from typing import Dict, Any

class BlockchainPlugin(BasePlugin):
    """Interface for blockchain integration plugins"""
    
    @abstractmethod
    async def connect(self, config: Dict[str, Any]) -> bool:
        """Connect to blockchain network"""
        pass
    
    @abstractmethod
    async def get_balance(self, address: str) -> Dict[str, Any]:
        """Get account balance"""
        pass
    
    @abstractmethod
    async def send_transaction(self, tx_data: Dict[str, Any]) -> str:
        """Send transaction and return hash"""
        pass
    
    @abstractmethod
    async def get_contract_events(self, contract_address: str, 
                                 event_name: str, 
                                 from_block: int = None) -> List[Dict[str, Any]]:
        """Get contract events"""
        pass

# Example blockchain plugin
class BitcoinPlugin(BlockchainPlugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="bitcoin-integration",
            version="1.0.0",
            description="Bitcoin blockchain integration",
            author="AITBC Team",
            license="MIT"
        )
    
    async def connect(self, config: Dict[str, Any]) -> bool:
        # Connect to Bitcoin node
        return True
```

#### AI/ML Plugin Interface

```python
from typing import List, Dict, Any

class AIPlugin(BasePlugin):
    """Interface for AI/ML plugins"""
    
    @abstractmethod
    async def predict(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Make prediction using AI model"""
        pass
    
    @abstractmethod
    async def train(self, training_data: List[Dict[str, Any]]) -> bool:
        """Train AI model"""
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        pass

# Example AI plugin
class TranslationAIPlugin(AIPlugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="translation-ai",
            version="1.0.0",
            description="AI-powered translation service",
            author="AITBC Team",
            license="MIT"
        )
    
    async def predict(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        # Translate text
        return {"translated_text": "Translated text"}
```

## Plugin Manager

### Plugin Manager Interface

```python
from typing import Dict, List, Optional
import asyncio

class PluginManager:
    """Central plugin management system"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.plugins: Dict[str, BasePlugin] = {}
        self.plugin_registry = PluginRegistry()
    
    async def load_plugin(self, plugin_name: str) -> bool:
        """Load a plugin by name"""
        pass
    
    async def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin"""
        pass
    
    async def start_plugin(self, plugin_name: str) -> bool:
        """Start a plugin"""
        pass
    
    async def stop_plugin(self, plugin_name: str) -> bool:
        """Stop a plugin"""
        pass
    
    def get_plugin_status(self, plugin_name: str) -> PluginStatus:
        """Get plugin status"""
        pass
    
    def list_plugins(self) -> List[str]:
        """List all loaded plugins"""
        pass
    
    async def broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcast event to all plugins"""
        pass
```

## Plugin Lifecycle

### State Transitions

```
UNLOADED → LOADING → LOADED → ACTIVE → INACTIVE → UNLOADING → UNLOADED
                ↓           ↓        ↓
              ERROR      ERROR    ERROR
```

### Lifecycle Methods

1. **Loading**: Plugin discovery and metadata loading
2. **Initialization**: Plugin setup and dependency resolution
3. **Starting**: Plugin activation and service registration
4. **Running**: Normal operation with event handling
5. **Stopping**: Graceful shutdown and cleanup
6. **Unloading**: Resource cleanup and removal

## Plugin Configuration

### Configuration Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "plugins": {
      "type": "object",
      "patternProperties": {
        "^[a-zA-Z][a-zA-Z0-9-]*$": {
          "type": "object",
          "properties": {
            "enabled": {"type": "boolean"},
            "priority": {"type": "integer", "minimum": 1, "maximum": 100},
            "config": {"type": "object"},
            "dependencies": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["enabled"]
        }
      }
    },
    "plugin_paths": {
      "type": "array",
      "items": {"type": "string"}
    },
    "auto_load": {"type": "boolean"},
    "health_check_interval": {"type": "integer", "minimum": 1}
  }
}
```

### Example Configuration

```yaml
plugins:
  agent-cli:
    enabled: true
    priority: 10
    config:
      default_agent_type: "chat"
      max_agents: 100
  
  bitcoin-integration:
    enabled: true
    priority: 20
    config:
      rpc_url: "http://localhost:8332"
      rpc_user: "bitcoin"
      rpc_password: "password"
  
  translation-ai:
    enabled: false
    priority: 30
    config:
      provider: "openai"
      api_key: "${OPENAI_API_KEY}"

plugin_paths:
  - "/opt/aitbc/plugins"
  - "~/.aitbc/plugins"
  - "./plugins"

auto_load: true
health_check_interval: 60
```

## Plugin Development Guidelines

### Best Practices

1. **Interface Compliance**: Always implement the required interface methods
2. **Error Handling**: Implement proper error handling and logging
3. **Resource Management**: Clean up resources in cleanup method
4. **Configuration**: Use configuration schema for validation
5. **Testing**: Include comprehensive tests for plugin functionality
6. **Documentation**: Provide clear documentation and examples

### Plugin Structure

```
my-plugin/
├── __init__.py
├── plugin.py          # Main plugin implementation
├── config_schema.json # Configuration schema
├── tests/
│   ├── __init__.py
│   └── test_plugin.py
├── docs/
│   ├── README.md
│   └── configuration.md
├── requirements.txt
└── setup.py
```

### Example Plugin Implementation

```python
# my-plugin/plugin.py
from aitbc.plugins import BasePlugin, PluginMetadata, PluginContext

class MyPlugin(BasePlugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="Example plugin",
            author="Developer Name",
            license="MIT"
        )
    
    async def initialize(self) -> bool:
        self.context.logger.info("Initializing my-plugin")
        # Setup plugin resources
        return True
    
    async def start(self) -> bool:
        self.context.logger.info("Starting my-plugin")
        # Start plugin services
        return True
    
    async def stop(self) -> bool:
        self.context.logger.info("Stopping my-plugin")
        # Stop plugin services
        return True
    
    async def cleanup(self) -> bool:
        self.context.logger.info("Cleaning up my-plugin")
        # Cleanup resources
        return True
```

## Plugin Registry

### Registry Format

```json
{
  "plugins": [
    {
      "name": "agent-cli",
      "version": "1.0.0",
      "description": "Agent management CLI commands",
      "author": "AITBC Team",
      "license": "MIT",
      "repository": "https://github.com/aitbc/agent-cli-plugin",
      "download_url": "https://pypi.org/project/aitbc-agent-cli/",
      "checksum": "sha256:...",
      "tags": ["cli", "agent", "management"],
      "compatibility": {
        "min_aitbc_version": "1.0.0",
        "max_aitbc_version": "2.0.0"
      }
    }
  ]
}
```

### Plugin Discovery

1. **Local Discovery**: Scan configured plugin directories
2. **Remote Discovery**: Query plugin registry for available plugins
3. **Dependency Resolution**: Resolve plugin dependencies
4. **Compatibility Check**: Verify version compatibility

## Security Considerations

### Plugin Sandboxing

- Plugins run in isolated environments
- Resource limits enforced (CPU, memory, network)
- File system access restricted to plugin directories
- Network access controlled by permissions

### Plugin Verification

- Digital signatures for plugin verification
- Checksum validation for plugin integrity
- Dependency scanning for security vulnerabilities
- Code review process for official plugins

## Testing

### Plugin Testing Framework

```python
import pytest
from aitbc.plugins.testing import PluginTestCase

class TestMyPlugin(PluginTestCase):
    def test_plugin_metadata(self):
        plugin = self.create_plugin(MyPlugin)
        metadata = plugin.get_metadata()
        assert metadata.name == "my-plugin"
        assert metadata.version == "1.0.0"
    
    async def test_plugin_lifecycle(self):
        plugin = self.create_plugin(MyPlugin)
        
        assert await plugin.initialize() is True
        assert await plugin.start() is True
        assert await plugin.stop() is True
        assert await plugin.cleanup() is True
    
    async def test_plugin_health_check(self):
        plugin = self.create_plugin(MyPlugin)
        await plugin.initialize()
        await plugin.start()
        
        health = await plugin.health_check()
        assert health["status"] == "active"
```

## Migration and Compatibility

### Version Compatibility

- Semantic versioning for plugin compatibility
- Migration path for breaking changes
- Deprecation warnings for obsolete interfaces
- Backward compatibility maintenance

### Plugin Migration

```python
# Legacy plugin interface (deprecated)
class LegacyPlugin:
    def old_method(self):
        pass

# Migration adapter
class LegacyPluginAdapter(BasePlugin):
    def __init__(self, legacy_plugin):
        self.legacy = legacy_plugin
    
    async def initialize(self) -> bool:
        # Migrate legacy initialization
        return True
```

## Performance Considerations

### Plugin Performance

- Lazy loading for plugins
- Resource pooling for shared resources
- Caching for plugin metadata
- Async/await for non-blocking operations

### Monitoring

- Plugin performance metrics
- Resource usage tracking
- Error rate monitoring
- Health check endpoints

## Conclusion

The AITBC plugin interface provides a flexible, extensible architecture for adding functionality to the platform. By following this specification, developers can create plugins that integrate seamlessly with the AITBC ecosystem while maintaining security, performance, and compatibility standards.

For more information and examples, see the plugin development documentation and sample plugins in the repository.
