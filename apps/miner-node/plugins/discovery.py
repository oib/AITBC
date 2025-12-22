"""
Plugin discovery and matching system
"""

import asyncio
import logging
from typing import Dict, List, Set, Optional
import requests

from .registry import registry
from .base import ServicePlugin
from .exceptions import PluginNotFoundError

logger = logging.getLogger(__name__)


class ServiceDiscovery:
    """Discovers and matches services to plugins"""
    
    def __init__(self, pool_hub_url: str, miner_id: str):
        self.pool_hub_url = pool_hub_url
        self.miner_id = miner_id
        self.enabled_services: Set[str] = set()
        self.service_configs: Dict[str, Dict] = {}
        self._last_update = 0
        self._update_interval = 60  # seconds
    
    async def start(self) -> None:
        """Start the discovery service"""
        logger.info("Starting service discovery")
        
        # Initialize plugin registry
        await registry.initialize()
        
        # Initial sync
        await self.sync_services()
        
        # Start background sync task
        asyncio.create_task(self._sync_loop())
    
    async def sync_services(self) -> None:
        """Sync enabled services from pool-hub"""
        try:
            # Get service configurations from pool-hub
            response = requests.get(
                f"{self.pool_hub_url}/v1/services/",
                headers={"X-Miner-ID": self.miner_id}
            )
            response.raise_for_status()
            
            services = response.json()
            
            # Update local state
            new_enabled = set()
            new_configs = {}
            
            for service in services:
                if service.get("enabled", False):
                    service_id = service["service_type"]
                    new_enabled.add(service_id)
                    new_configs[service_id] = service
            
            # Find changes
            added = new_enabled - self.enabled_services
            removed = self.enabled_services - new_enabled
            updated = set()
            
            for service_id in self.enabled_services & new_enabled:
                if new_configs[service_id] != self.service_configs.get(service_id):
                    updated.add(service_id)
            
            # Apply changes
            for service_id in removed:
                await self._disable_service(service_id)
            
            for service_id in added:
                await self._enable_service(service_id, new_configs[service_id])
            
            for service_id in updated:
                await self._update_service(service_id, new_configs[service_id])
            
            # Update state
            self.enabled_services = new_enabled
            self.service_configs = new_configs
            self._last_update = asyncio.get_event_loop().time()
            
            logger.info(f"Synced services: {len(self.enabled_services)} enabled")
            
        except Exception as e:
            logger.error(f"Failed to sync services: {e}")
    
    async def _enable_service(self, service_id: str, config: Dict) -> None:
        """Enable a service"""
        try:
            # Check if plugin exists
            if service_id not in registry.list_plugins():
                logger.warning(f"No plugin available for service: {service_id}")
                return
            
            # Load plugin
            plugin = registry.load_plugin(service_id)
            
            # Validate hardware requirements
            await self._validate_hardware_requirements(plugin, config)
            
            # Configure plugin if needed
            if hasattr(plugin, 'configure'):
                await plugin.configure(config.get('config', {}))
            
            logger.info(f"Enabled service: {service_id}")
            
        except Exception as e:
            logger.error(f"Failed to enable service {service_id}: {e}")
    
    async def _disable_service(self, service_id: str) -> None:
        """Disable a service"""
        try:
            # Unload plugin to free resources
            registry.unload_plugin(service_id)
            logger.info(f"Disabled service: {service_id}")
            
        except Exception as e:
            logger.error(f"Failed to disable service {service_id}: {e}")
    
    async def _update_service(self, service_id: str, config: Dict) -> None:
        """Update service configuration"""
        # For now, just disable and re-enable
        await self._disable_service(service_id)
        await self._enable_service(service_id, config)
    
    async def _validate_hardware_requirements(self, plugin: ServicePlugin, config: Dict) -> None:
        """Validate that miner meets plugin requirements"""
        requirements = plugin.get_hardware_requirements()
        
        # This would check against actual miner hardware
        # For now, just log the requirements
        logger.debug(f"Hardware requirements for {plugin.service_id}: {requirements}")
    
    async def _sync_loop(self) -> None:
        """Background sync loop"""
        while True:
            await asyncio.sleep(self._update_interval)
            await self.sync_services()
    
    async def execute_service(self, service_id: str, request: Dict) -> Dict:
        """Execute a service request"""
        try:
            # Check if service is enabled
            if service_id not in self.enabled_services:
                raise PluginNotFoundError(f"Service {service_id} is not enabled")
            
            # Get plugin
            plugin = registry.get_plugin(service_id)
            if not plugin:
                raise PluginNotFoundError(f"No plugin loaded for service: {service_id}")
            
            # Execute request
            result = await plugin.execute(request)
            
            # Convert result to dict
            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "metrics": result.metrics,
                "execution_time": result.execution_time
            }
            
        except Exception as e:
            logger.error(f"Failed to execute service {service_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_enabled_services(self) -> List[str]:
        """Get list of enabled services"""
        return list(self.enabled_services)
    
    def get_service_status(self) -> Dict[str, Dict]:
        """Get status of all services"""
        status = {}
        
        for service_id in registry.list_plugins():
            plugin = registry.get_plugin(service_id)
            status[service_id] = {
                "enabled": service_id in self.enabled_services,
                "loaded": plugin is not None,
                "config": self.service_configs.get(service_id, {}),
                "capabilities": plugin.capabilities if plugin else []
            }
        
        return status
    
    async def health_check(self) -> Dict[str, bool]:
        """Health check all enabled services"""
        results = {}
        
        for service_id in self.enabled_services:
            plugin = registry.get_plugin(service_id)
            if plugin:
                try:
                    results[service_id] = await plugin.health_check()
                except Exception as e:
                    logger.error(f"Health check failed for {service_id}: {e}")
                    results[service_id] = False
            else:
                results[service_id] = False
        
        return results
    
    async def stop(self) -> None:
        """Stop the discovery service"""
        logger.info("Stopping service discovery")
        registry.cleanup_all()
