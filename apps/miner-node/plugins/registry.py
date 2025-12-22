"""
Plugin registry for managing service plugins
"""

from typing import Dict, List, Type, Optional
import importlib
import inspect
import logging
from pathlib import Path

from .base import ServicePlugin
from .exceptions import PluginError, PluginNotFoundError

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for managing service plugins"""
    
    def __init__(self):
        self._plugins: Dict[str, ServicePlugin] = {}
        self._plugin_classes: Dict[str, Type[ServicePlugin]] = {}
        self._loaded = False
    
    def register(self, plugin_class: Type[ServicePlugin]) -> None:
        """Register a plugin class"""
        plugin_id = getattr(plugin_class, "service_id", plugin_class.__name__)
        self._plugin_classes[plugin_id] = plugin_class
        logger.info(f"Registered plugin class: {plugin_id}")
    
    def load_plugin(self, service_id: str) -> ServicePlugin:
        """Load and instantiate a plugin"""
        if service_id not in self._plugin_classes:
            raise PluginNotFoundError(f"Plugin {service_id} not found")
        
        if service_id in self._plugins:
            return self._plugins[service_id]
        
        try:
            plugin_class = self._plugin_classes[service_id]
            plugin = plugin_class()
            plugin.setup()
            self._plugins[service_id] = plugin
            logger.info(f"Loaded plugin: {service_id}")
            return plugin
        except Exception as e:
            logger.error(f"Failed to load plugin {service_id}: {e}")
            raise PluginError(f"Failed to load plugin {service_id}: {e}")
    
    def get_plugin(self, service_id: str) -> Optional[ServicePlugin]:
        """Get loaded plugin"""
        return self._plugins.get(service_id)
    
    def unload_plugin(self, service_id: str) -> None:
        """Unload a plugin"""
        if service_id in self._plugins:
            plugin = self._plugins[service_id]
            plugin.cleanup()
            del self._plugins[service_id]
            logger.info(f"Unloaded plugin: {service_id}")
    
    def list_plugins(self) -> List[str]:
        """List all registered plugin IDs"""
        return list(self._plugin_classes.keys())
    
    def list_loaded_plugins(self) -> List[str]:
        """List all loaded plugin IDs"""
        return list(self._plugins.keys())
    
    async def load_all_from_directory(self, plugin_dir: Path) -> None:
        """Load all plugins from a directory"""
        if not plugin_dir.exists():
            logger.warning(f"Plugin directory does not exist: {plugin_dir}")
            return
        
        for plugin_file in plugin_dir.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue
            
            module_name = plugin_file.stem
            try:
                # Import the module
                spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find plugin classes in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, ServicePlugin) and 
                        obj != ServicePlugin and 
                        not name.startswith("_")):
                        self.register(obj)
                        logger.info(f"Auto-registered plugin from {module_name}: {name}")
                        
            except Exception as e:
                logger.error(f"Failed to load plugin from {plugin_file}: {e}")
    
    async def initialize(self, plugin_dir: Optional[Path] = None) -> None:
        """Initialize the plugin registry"""
        if self._loaded:
            return
        
        # Load built-in plugins
        from . import whisper, stable_diffusion, llm_inference, ffmpeg, blender
        
        self.register(whisper.WhisperPlugin)
        self.register(stable_diffusion.StableDiffusionPlugin)
        self.register(llm_inference.LLMPlugin)
        self.register(ffmpeg.FFmpegPlugin)
        self.register(blender.BlenderPlugin)
        
        # Load external plugins if directory provided
        if plugin_dir:
            await self.load_all_from_directory(plugin_dir)
        
        self._loaded = True
        logger.info(f"Plugin registry initialized with {len(self._plugin_classes)} plugins")
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Health check all loaded plugins"""
        results = {}
        for service_id, plugin in self._plugins.items():
            try:
                results[service_id] = await plugin.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {service_id}: {e}")
                results[service_id] = False
        return results
    
    def cleanup_all(self) -> None:
        """Cleanup all loaded plugins"""
        for service_id in list(self._plugins.keys()):
            self.unload_plugin(service_id)
        logger.info("All plugins cleaned up")


# Global registry instance
registry = PluginRegistry()
