"""
Plugin system exceptions
"""


class PluginError(Exception):
    """Base exception for plugin errors"""
    pass


class PluginNotFoundError(PluginError):
    """Raised when a plugin is not found"""
    pass


class PluginValidationError(PluginError):
    """Raised when plugin validation fails"""
    pass


class PluginExecutionError(PluginError):
    """Raised when plugin execution fails"""
    pass
