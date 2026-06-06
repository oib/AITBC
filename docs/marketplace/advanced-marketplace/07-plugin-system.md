# Plugin System

## Overview

The PluginManager provides a production-ready plugin system for marketplace extensions.

## Features

### Plugin Registration
- Register plugins with metadata
- Enable/disable plugins
- Plugin configuration management

### Plugin Hooks
- `before_booking`: Pre-booking hook
- `after_booking`: Post-booking hook
- `before_pricing`: Pre-pricing hook
- `after_pricing`: Post-pricing hook
- `before_auction`: Pre-auction hook
- `after_auction`: Post-auction hook

### Hook Execution
- Sequential hook execution
- Context passing
- Error handling

## Usage Example

```python
from app.contexts.marketplace.services.plugin_manager import get_plugin_manager

# Get plugin manager
plugin_manager = get_plugin_manager()

# Register plugin
plugin = plugin_manager.register_plugin(
    plugin_name="custom-pricing",
    plugin_version="1.0.0",
    plugin_type="extension",
    description="Custom pricing algorithm",
    author="AITBC"
)

# Register hook
def custom_pricing_hook(context):
    # Custom pricing logic
    context["custom_price"] = context["base_price"] * 1.1
    return context

plugin_manager.register_hook("before_pricing", custom_pricing_hook)

# Enable plugin
plugin_manager.enable_plugin("custom-pricing")

# Execute hooks in service
service = MarketplaceService(session)
context = service.before_pricing(
    resource_id="gpu-789",
    base_price=0.50
)
```
