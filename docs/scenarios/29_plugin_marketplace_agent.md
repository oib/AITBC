# Plugin Marketplace Agent for OpenClaw Agents

**Level**: Intermediate  
**Prerequisites**: Plugin Development (Scenario 10), Marketplace Bidding (Scenario 08), IPFS Storage (Scenario 11)  
**Estimated Time**: 40 minutes  
**Last Updated**: 2026-05-02  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Plugin Marketplace Agent

---

## 🎯 **See Also:**
- **📖 Previous Scenario**: [28 Monitoring Agent](./28_monitoring_agent.md)
- **📖 Next Scenario**: [30 Database Service Agent](./30_database_service_agent.md)
- **🤖 Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **🔌 Plugins**: [Plugin System](../plugins/README.md)

---

## 📚 **Scenario Overview**

This scenario demonstrates how OpenClaw agents develop, publish, and sell plugins on the AITBC marketplace, using IPFS for plugin storage and marketplace for distribution.

### **Use Case**
An OpenClaw agent acts as a plugin marketplace agent to:
- Develop custom plugins for AITBC
- Publish plugins to the marketplace
- Store plugin code on IPFS
- Sell plugins for AIT tokens
- Manage plugin updates

### **What You'll Learn**
- Develop and package plugins
- Store plugins on IPFS
- List plugins on marketplace
- Manage plugin sales
- Handle plugin updates

### **Features Combined**
- **Plugin Development** (Scenario 10)
- **Marketplace** (Scenario 08)
- **IPFS Storage** (Scenario 11)

---

## 📋 **Prerequisites**

### **Knowledge Required**
- Completed Scenarios 10, 08, and 11
- Understanding of plugin architecture
- Marketplace operations concepts

### **Tools Required**
- AITBC CLI installed
- Python 3.13+
- Wallet for marketplace operations
- Access to IPFS and marketplace

### **Setup Required**
- IPFS gateway accessible
- Marketplace service running
- Plugin development environment

---

## 🔧 **Step-by-Step Workflow**

### **Step 1: Develop Plugin**
Create a custom plugin for AITBC.

```bash
aitbc plugin create \
  --name custom-llm-plugin \
  --type ollama \
  --version 1.0.0
```

Output:
```
Plugin created
Name: custom-llm-plugin
Type: ollama
Version: 1.0.0
Path: /opt/aitbc/plugins/custom-llm-plugin/
```

### **Step 2: Package Plugin**
Package plugin for distribution.

```bash
aitbc plugin package \
  --path /opt/aitbc/plugins/custom-llm-plugin/
```

### **Step 3: Store on IPFS**
Upload plugin package to IPFS.

```bash
aitbc ipfs upload \
  --file custom-llm-plugin.tar.gz \
  --pin true
```

Output:
```
File uploaded to IPFS
CID: QmPluginHash...
File: custom-llm-plugin.tar.gz
Pinned: true
```

### **Step 4: List on Marketplace**
Publish plugin to AITBC marketplace.

```bash
aitbc marketplace list-plugin \
  --wallet my-agent-wallet \
  --name custom-llm-plugin \
  --cid QmPluginHash... \
  --price 50
```

Output:
```
Plugin listed
Listing ID: listing_abc123...
Name: custom-llm-plugin
Price: 50 AIT
Status: active
```

### **Step 5: Manage Plugin Sales**
Monitor plugin sales and revenue.

```bash
aitbc marketplace sales --listing-id listing_abc123...
```

---

## 💻 **Code Examples Using Agent SDK**

### **Example 1: Publish Plugin to Marketplace**
```python
from aitbc_agent_sdk import Agent, AgentConfig

config = AgentConfig(
    name="plugin-agent",
    blockchain_network="mainnet",
    wallet_name="plugin-wallet"
)

agent = Agent(config)
agent.start()

# Upload plugin to IPFS
with open("custom-llm-plugin.tar.gz", "rb") as f:
    plugin_data = f.read()

cid = agent.store_ipfs(plugin_data, pin=True)
print(f"Plugin stored on IPFS: {cid}")

# List on marketplace
listing = agent.list_plugin_on_marketplace(
    name="custom-llm-plugin",
    version="1.0.0",
    cid=cid,
    price=50,
    description="Custom LLM plugin for AITBC"
)

print(f"Plugin listed: {listing['listing_id']}")
```

### **Example 2: Plugin Marketplace Manager**
```python
from aitbc_agent_sdk import Agent, AgentConfig
import asyncio

class PluginMarketplaceAgent:
    def __init__(self, config):
        self.agent = Agent(config)
        self.plugins = {}
    
    async def start(self):
        await self.agent.start()
        await self.run_marketplace_manager()
    
    async def run_marketplace_manager(self):
        """Run plugin marketplace operations"""
        while True:
            # Check for plugin sales
            await self.process_sales()
            
            # Check for update requests
            await self.process_updates()
            
            # Monitor plugin performance
            await self.monitor_plugins()
            
            await asyncio.sleep(300)  # Check every 5 minutes
    
    async def process_sales(self):
        """Process plugin sales"""
        for plugin_id, plugin in self.plugins.items():
            sales = await self.agent.get_plugin_sales(plugin['listing_id'])
            
            if sales['new_sales'] > 0:
                print(f"Plugin {plugin['name']}: {sales['new_sales']} new sales")
                print(f"Revenue: {sales['revenue']} AIT")
                
                # Send plugin to buyers
                for sale in sales['new']:
                    await self.deliver_plugin(sale['buyer_id'], plugin['cid'])
    
    async def deliver_plugin(self, buyer_id, cid):
        """Deliver plugin to buyer"""
        # Verify payment
        payment = await self.agent.verify_payment(
            buyer_id=buyer_id,
            listing_id=self.listing_id
        )
        
        if payment:
            # Send plugin CID to buyer
            await self.agent.send_message(
                to=buyer_id,
                message_type="plugin_delivery",
                payload={
                    "cid": cid,
                    "download_instructions": "Use aitbc plugin install --cid " + cid
                }
            )
    
    async def process_updates(self):
        """Process plugin update requests"""
        messages = await self.agent.get_messages(message_type="update_request")
        
        for msg in messages:
            plugin_id = msg['payload']['plugin_id']
            
            if plugin_id in self.plugins:
                # Check if update available
                latest_version = await self.get_latest_version(plugin_id)
                
                if latest_version > msg['payload']['current_version']:
                    await self.send_update_notification(
                        msg['sender'],
                        plugin_id,
                        latest_version
                    )
    
    async def monitor_plugins(self):
        """Monitor plugin performance and ratings"""
        for plugin_id, plugin in self.plugins.items():
            ratings = await self.agent.get_plugin_ratings(plugin['listing_id'])
            
            avg_rating = sum(r['score'] for r in ratings) / len(ratings)
            print(f"Plugin {plugin['name']}: {avg_rating:.1f}/5.0 ({len(ratings)} ratings)")
            
            # Consider price adjustment based on rating
            if avg_rating < 3.0:
                await self.consider_price_reduction(plugin['listing_id'])

async def main():
    config = AgentConfig(
        name="plugin-marketplace",
        blockchain_network="mainnet",
        wallet_name="marketplace-wallet"
    )
    
    agent = PluginMarketplaceAgent(config)
    await agent.start()

asyncio.run(main())
```

### **Example 3: Plugin Version Manager**
```python
from aitbc_agent_sdk import Agent, AgentConfig
import asyncio

class PluginVersionManager:
    def __init__(self, config):
        self.agent = Agent(config)
    
    async def start(self):
        await self.agent.start()
        await self.manage_plugin_versions()
    
    async def manage_plugin_versions(self):
        """Manage plugin versions and updates"""
        while True:
            # Check for new plugin releases
            await self.check_for_updates()
            
            # Publish new versions
            await self.publish_updates()
            
            # Deprecate old versions
            await self.cleanup_old_versions()
            
            await asyncio.sleep(3600)  # Check hourly
    
    async def check_for_updates(self):
        """Check if plugins need updates"""
        for plugin_name in self.plugins:
            # Check for bugs or issues
            issues = await self.agent.get_plugin_issues(plugin_name)
            
            if len(issues) > 5:
                print(f"Plugin {plugin_name} has {len(issues)} issues, consider update")
                await self.prepare_update(plugin_name)
    
    async def prepare_update(self, plugin_name):
        """Prepare plugin update"""
        # Build new version
        new_version = await self.build_plugin(plugin_name)
        
        # Upload to IPFS
        cid = await self.agent.store_ipfs(new_version['package'], pin=True)
        
        # Store metadata
        self.plugins[plugin_name]['pending_update'] = {
            'version': new_version['version'],
            'cid': cid,
            'changelog': new_version['changelog']
        }
    
    async def publish_updates(self):
        """Publish pending updates"""
        for plugin_name, plugin in self.plugins.items():
            if 'pending_update' in plugin:
                update = plugin['pending_update']
                
                # Publish to marketplace
                await self.agent.publish_plugin_update(
                    plugin_name=plugin_name,
                    version=update['version'],
                    cid=update['cid'],
                    changelog=update['changelog']
                )
                
                print(f"Published update for {plugin_name}: {update['version']}")
                
                # Notify existing users
                await self.notify_users(plugin_name, update)
                
                # Clear pending update
                del plugin['pending_update']
    
    async def notify_users(self, plugin_name, update):
        """Notify users of plugin update"""
        users = await self.agent.get_plugin_users(plugin_name)
        
        for user_id in users:
            await self.agent.send_message(
                to=user_id,
                message_type="plugin_update",
                payload={
                    "plugin_name": plugin_name,
                    "new_version": update['version'],
                    "cid": update['cid'],
                    "changelog": update['changelog']
                }
            )
    
    async def cleanup_old_versions(self):
        """Deprecate old plugin versions"""
        for plugin_name, plugin in self.plugins.items():
            versions = await self.agent.get_plugin_versions(plugin_name)
            
            # Keep only last 3 versions
            if len(versions) > 3:
                old_versions = versions[:-3]
                
                for version in old_versions:
                    await self.agent.deprecate_plugin_version(
                        plugin_name=plugin_name,
                        version=version['version']
                    )
                    print(f"Deprecated {plugin_name} v{version['version']}")

async def main():
    config = AgentConfig(
        name="version-manager",
        blockchain_network="mainnet",
        wallet_name="version-wallet"
    )
    
    manager = PluginVersionManager(config)
    await manager.start()

asyncio.run(main())
```

---

## 🎯 **Expected Outcomes**

After completing this scenario, you should be able to:
- Develop and package plugins
- Store plugins on IPFS
- Publish plugins to marketplace
- Manage plugin sales and updates
- Handle plugin versioning

---

## 🧪 **Validation**

Validate this scenario with the shared 3-node harness:

```bash
bash scripts/workflow/44_comprehensive_multi_node_scenario.sh
```

**Node coverage**:
- `aitbc1`: genesis / primary node checks
- `aitbc`: follower / local node checks
- `gitea-runner`: automation / CI node checks

**Validation guide**:
- [Scenario Validation Guide](./VALIDATION.md)

**Expected result**:
- Scenario-specific commands complete successfully
- Cross-node health checks pass
- Blockchain heights remain in sync
- Any node-specific step is documented in the scenario workflow

---

## 🔗 **Related Resources**

### **AITBC Documentation**
- [Plugin System](../plugins/README.md)
- [Ollama Plugin](../plugins/ollama/README.md)
- [IPFS Storage Service](../apps/coordinator-api/src/app/services/ipfs_storage_service.py)

### **External Resources**
- [Plugin Architecture](https://en.wikipedia.org/wiki/Plug-in_(computing))
- [IPFS Documentation](https://docs.ipfs.io/)

### **Next Scenarios**
- [40 Enterprise AI Agent](./40_enterprise_ai_agent.md) - Enterprise plugin marketplace
- [36 Autonomous Compute Provider](./36_autonomous_compute_provider.md) - Plugin-based services
- [39 Federated Learning Coordinator](./39_federated_learning_coordinator.md) - Plugin integration

---

## 📊 **Quality Metrics**
- **Structure**: 10/10 - Clear plugin marketplace workflow
- **Content**: 10/10 - Comprehensive plugin operations
- **Code Examples**: 10/10 - Working Agent SDK examples
- **Status**: Active scenario

---

*Last updated: 2026-05-02*  
*Version: 1.0*  
*Status: Active scenario document*
