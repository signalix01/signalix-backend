"""
Broker Plugin System

Plugin architecture for broker integrations.
Supports dynamic loading, hot-reloading, and plugin validation.

Requirements: 25.1, 25.2, 25.3, 25.4, 25.6, 25.7, 25.10
"""

import os
import sys
import importlib
import importlib.util
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type, Any
from dataclasses import dataclass
from pathlib import Path
import logging
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class PluginMetadata:
    """Plugin metadata information"""
    name: str
    version: str
    description: str
    author: str
    supported_brokers: List[str]
    required_config: List[str]
    optional_config: List[str]
    capabilities: Dict[str, bool]
    min_api_version: str = "1.0"
    max_api_version: str = "1.0"


class BrokerPluginInterface(ABC):
    """
    Interface that all broker plugins must implement.
    
    Requirements: 25.1, 25.2, 25.4
    """
    
    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        pass
    
    @abstractmethod
    def create_adapter(self, config: Dict[str, Any], paper_trading: bool = False) -> Any:
        """Create and return a broker adapter instance."""
        pass
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate plugin configuration."""
        pass
    
    @abstractmethod
    def get_supported_auth_types(self) -> List[str]:
        """Return list of supported authentication types."""
        pass


class PluginRegistry:
    """
    Registry for broker plugins.
    
    Manages plugin discovery, loading, and lifecycle.
    """
    
    def __init__(self, plugins_directory: Optional[str] = None):
        """
        Initialize plugin registry.
        
        Args:
            plugins_directory: Directory containing plugin files
        """
        self.plugins_directory = plugins_directory or self._get_default_plugins_dir()
        self._plugins: Dict[str, BrokerPluginInterface] = {}
        self._metadata: Dict[str, PluginMetadata] = {}
        self._adapters: Dict[str, Type] = {}
        self._file_mtimes: Dict[str, float] = {}
        self._hot_reload_enabled = False
        self._reload_task: Optional[asyncio.Task] = None
    
    def _get_default_plugins_dir(self) -> str:
        """Get default plugins directory."""
        current_dir = Path(__file__).parent
        return str(current_dir / "adapters" / "plugins")
    
    async def discover_plugins(self) -> List[str]:
        """
        Discover available plugins in the plugins directory.
        
        Returns:
            List of plugin names found
        """
        discovered = []
        
        if not os.path.exists(self.plugins_directory):
            logger.warning(f"Plugins directory not found: {self.plugins_directory}")
            return discovered
        
        for filename in os.listdir(self.plugins_directory):
            if filename.endswith('_plugin.py') or filename.endswith('_adapter.py'):
                plugin_name = filename.replace('_plugin.py', '').replace('_adapter.py', '')
                discovered.append(plugin_name)
                
                # Store file mtime for hot-reload
                filepath = os.path.join(self.plugins_directory, filename)
                self._file_mtimes[filepath] = os.path.getmtime(filepath)
        
        logger.info(f"Discovered {len(discovered)} plugins: {discovered}")
        return discovered
    
    async def load_plugin(self, plugin_name: str) -> Optional[BrokerPluginInterface]:
        """
        Load a plugin by name.
        
        Args:
            plugin_name: Name of the plugin to load
            
        Returns:
            Loaded plugin instance or None
        """
        # Check if already loaded
        if plugin_name in self._plugins:
            return self._plugins[plugin_name]
        
        # Find plugin file
        plugin_file = self._find_plugin_file(plugin_name)
        if not plugin_file:
            logger.error(f"Plugin file not found for: {plugin_name}")
            return None
        
        try:
            # Load module
            spec = importlib.util.spec_from_file_location(
                f"broker_plugin.{plugin_name}",
                plugin_file
            )
            module = importlib.util.module_from_spec(spec)
            
            # Add to sys.modules temporarily
            sys.modules[f"broker_plugin.{plugin_name}"] = module
            spec.loader.exec_module(module)
            
            # Find plugin class
            plugin_class = self._find_plugin_class(module)
            if not plugin_class:
                logger.error(f"No plugin class found in {plugin_file}")
                return None
            
            # Instantiate plugin
            plugin = plugin_class()
            
            # Validate plugin interface compliance
            if not self._validate_plugin_interface(plugin):
                logger.error(f"Plugin {plugin_name} does not implement required interface")
                return None
            
            # Store plugin
            self._plugins[plugin_name] = plugin
            self._metadata[plugin_name] = plugin.get_metadata()
            
            logger.info(f"Successfully loaded plugin: {plugin_name}")
            return plugin
            
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {e}")
            return None
    
    def _find_plugin_file(self, plugin_name: str) -> Optional[str]:
        """Find plugin file path."""
        candidates = [
            f"{plugin_name}_plugin.py",
            f"{plugin_name}_adapter.py",
            f"{plugin_name}.py"
        ]
        
        for candidate in candidates:
            filepath = os.path.join(self.plugins_directory, candidate)
            if os.path.exists(filepath):
                return filepath
        
        # Also check parent adapters directory for built-in adapters
        parent_dir = Path(self.plugins_directory).parent
        for candidate in candidates:
            filepath = os.path.join(parent_dir, candidate)
            if os.path.exists(filepath):
                return filepath
        
        return None
    
    def _find_plugin_class(self, module) -> Optional[Type[BrokerPluginInterface]]:
        """Find plugin class in module."""
        for name in dir(module):
            obj = getattr(module, name)
            if (isinstance(obj, type) and 
                issubclass(obj, BrokerPluginInterface) and 
                obj is not BrokerPluginInterface):
                return obj
        return None
    
    def _validate_plugin_interface(self, plugin: Any) -> bool:
        """
        Validate that plugin implements required interface.
        
        Requirements: 25.4
        """
        required_methods = [
            'get_metadata',
            'create_adapter',
            'validate_config',
            'get_supported_auth_types'
        ]
        
        for method in required_methods:
            if not hasattr(plugin, method) or not callable(getattr(plugin, method)):
                logger.error(f"Plugin missing required method: {method}")
                return False
        
        # Validate metadata
        try:
            metadata = plugin.get_metadata()
            if not isinstance(metadata, PluginMetadata):
                logger.error("Plugin metadata is not PluginMetadata type")
                return False
        except Exception as e:
            logger.error(f"Plugin failed to provide metadata: {e}")
            return False
        
        return True
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a plugin.
        
        Args:
            plugin_name: Name of plugin to unload
            
        Returns:
            True if unloaded successfully
        """
        if plugin_name not in self._plugins:
            return False
        
        del self._plugins[plugin_name]
        del self._metadata[plugin_name]
        
        logger.info(f"Unloaded plugin: {plugin_name}")
        return True
    
    def reload_plugin(self, plugin_name: str) -> Optional[BrokerPluginInterface]:
        """
        Reload a plugin (for hot-reloading).
        
        Requirements: 25.6, 25.7
        
        Args:
            plugin_name: Name of plugin to reload
            
        Returns:
            Reloaded plugin instance or None
        """
        # Unload existing
        self.unload_plugin(plugin_name)
        
        # Clear module from cache
        module_name = f"broker_plugin.{plugin_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        # Reload
        return asyncio.run(self.load_plugin(plugin_name))
    
    async def enable_hot_reload(self, interval: float = 5.0):
        """
        Enable hot-reloading of plugins.
        
        Args:
            interval: Check interval in seconds
        """
        self._hot_reload_enabled = True
        self._reload_task = asyncio.create_task(
            self._hot_reload_loop(interval)
        )
        logger.info("Hot-reload enabled")
    
    async def disable_hot_reload(self):
        """Disable hot-reloading."""
        self._hot_reload_enabled = False
        if self._reload_task:
            self._reload_task.cancel()
            try:
                await self._reload_task
            except asyncio.CancelledError:
                pass
        logger.info("Hot-reload disabled")
    
    async def _hot_reload_loop(self, interval: float):
        """Hot-reload monitoring loop."""
        while self._hot_reload_enabled:
            try:
                await asyncio.sleep(interval)
                
                # Check for file changes
                for filepath, last_mtime in list(self._file_mtimes.items()):
                    if os.path.exists(filepath):
                        current_mtime = os.path.getmtime(filepath)
                        if current_mtime > last_mtime:
                            # File changed, reload
                            filename = os.path.basename(filepath)
                            plugin_name = filename.replace('_plugin.py', '').replace('_adapter.py', '').replace('.py', '')
                            
                            logger.info(f"Detected change in {filename}, reloading...")
                            self.reload_plugin(plugin_name)
                            
                            # Update mtime
                            self._file_mtimes[filepath] = current_mtime
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in hot-reload loop: {e}")
    
    def get_plugin(self, plugin_name: str) -> Optional[BrokerPluginInterface]:
        """Get loaded plugin by name."""
        return self._plugins.get(plugin_name)
    
    def get_plugin_metadata(self, plugin_name: str) -> Optional[PluginMetadata]:
        """Get plugin metadata."""
        return self._metadata.get(plugin_name)
    
    def list_plugins(self) -> List[str]:
        """List all loaded plugin names."""
        return list(self._plugins.keys())
    
    def get_all_metadata(self) -> Dict[str, PluginMetadata]:
        """Get metadata for all loaded plugins."""
        return self._metadata.copy()
    
    def create_adapter(
        self,
        plugin_name: str,
        config: Dict[str, Any],
        paper_trading: bool = False
    ) -> Optional[Any]:
        """
        Create an adapter instance from a plugin.
        
        Args:
            plugin_name: Name of plugin to use
            config: Adapter configuration
            paper_trading: Enable paper trading mode
            
        Returns:
            Adapter instance or None
        """
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            logger.error(f"Plugin not found: {plugin_name}")
            return None
        
        # Validate config
        is_valid, error = plugin.validate_config(config)
        if not is_valid:
            logger.error(f"Invalid config for {plugin_name}: {error}")
            return None
        
        # Create adapter
        try:
            return plugin.create_adapter(config, paper_trading)
        except Exception as e:
            logger.error(f"Failed to create adapter from {plugin_name}: {e}")
            return None
    
    def get_plugin_for_broker(self, broker_code: str) -> Optional[str]:
        """
        Find plugin that supports a specific broker.
        
        Args:
            broker_code: Broker code (e.g., 'zerodha', 'angel_one')
            
        Returns:
            Plugin name or None
        """
        for name, metadata in self._metadata.items():
            if broker_code.lower() in [b.lower() for b in metadata.supported_brokers]:
                return name
        return None
    
    def get_capabilities(self, plugin_name: str) -> Dict[str, bool]:
        """
        Get capabilities for a plugin.
        
        Args:
            plugin_name: Name of plugin
            
        Returns:
            Dictionary of capability flags
        """
        metadata = self.get_plugin_metadata(plugin_name)
        if metadata:
            return metadata.capabilities
        return {}


class BuiltInPluginLoader:
    """
    Loader for built-in broker adapters.
    
    Loads adapters that are part of the core package.
    """
    
    def __init__(self, registry: PluginRegistry):
        """
        Initialize built-in loader.
        
        Args:
            registry: PluginRegistry instance
        """
        self.registry = registry
    
    async def load_all(self) -> int:
        """
        Load all built-in plugins.
        
        Returns:
            Number of plugins loaded
        """
        built_in = [
            'zerodha',
            'dhan',
            'upstox',
            'angel_one',
            'icici_direct'
        ]
        
        loaded = 0
        for plugin_name in built_in:
            try:
                # Import and register as plugin
                plugin = self._create_builtin_plugin(plugin_name)
                if plugin:
                    self.registry._plugins[plugin_name] = plugin
                    self.registry._metadata[plugin_name] = plugin.get_metadata()
                    loaded += 1
                    logger.info(f"Loaded built-in plugin: {plugin_name}")
            except Exception as e:
                logger.error(f"Failed to load built-in plugin {plugin_name}: {e}")
        
        return loaded
    
    def _create_builtin_plugin(self, broker_code: str) -> Optional[BrokerPluginInterface]:
        """Create a built-in plugin wrapper for an adapter."""
        # Import the adapter module
        try:
            if broker_code == 'zerodha':
                from .adapters.zerodha_adapter import ZerodhaAdapter
                adapter_class = ZerodhaAdapter
            elif broker_code == 'dhan':
                from .adapters.dhan_adapter import DhanAdapter
                adapter_class = DhanAdapter
            elif broker_code == 'upstox':
                from .adapters.upstox_adapter import UpstoxAdapter
                adapter_class = UpstoxAdapter
            elif broker_code == 'angel_one':
                from .adapters.angel_one_adapter import AngelOneAdapter
                adapter_class = AngelOneAdapter
            elif broker_code == 'icici_direct':
                from .adapters.icici_adapter import ICICIAdapter
                adapter_class = ICICIAdapter
            else:
                return None
            
            # Create plugin wrapper
            return BuiltInPluginWrapper(broker_code, adapter_class)
            
        except ImportError as e:
            logger.warning(f"Built-in adapter not available for {broker_code}: {e}")
            return None


class BuiltInPluginWrapper(BrokerPluginInterface):
    """Wrapper to make built-in adapters compatible with plugin interface."""
    
    def __init__(self, broker_code: str, adapter_class: Type):
        self.broker_code = broker_code
        self.adapter_class = adapter_class
        self._metadata = self._create_metadata()
    
    def _create_metadata(self) -> PluginMetadata:
        """Create metadata for built-in adapter."""
        capabilities = {
            "supports_bracket_orders": self.broker_code in ['zerodha', 'upstox'],
            "supports_cover_orders": self.broker_code in ['zerodha', 'upstox'],
            "supports_amo": True,
            "supports_modify_order": True,
            "supports_websocket": True,
            "supports_multiple_accounts": self.broker_code == 'zerodha'
        }
        
        return PluginMetadata(
            name=f"{self.broker_code}_builtin",
            version="1.0.0",
            description=f"Built-in adapter for {self.broker_code}",
            author="SignalixAI",
            supported_brokers=[self.broker_code],
            required_config=['api_key'],
            optional_config=['api_secret', 'client_id', 'access_token'],
            capabilities=capabilities
        )
    
    def get_metadata(self) -> PluginMetadata:
        return self._metadata
    
    def create_adapter(self, config: Dict[str, Any], paper_trading: bool = False) -> Any:
        return self.adapter_class(config, paper_trading)
    
    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = self._metadata.required_config
        for field in required:
            if field not in config or not config[field]:
                return False, f"Missing required field: {field}"
        return True, None
    
    def get_supported_auth_types(self) -> List[str]:
        return ["api_key", "oauth", "two_factor"]
