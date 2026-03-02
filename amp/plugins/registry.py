"""Plugin registry for amp — auto-discovery and per-user enable/disable."""
import importlib
import pkgutil

from amp.plugins.base import BasePlugin


class PluginRegistry:
    def __init__(self):
        self._plugins: dict[str, BasePlugin] = {}

    def register(self, plugin: BasePlugin) -> None:
        self._plugins[plugin.name] = plugin

    def discover(self) -> None:
        """Auto-discover plugins in amp/plugins/ directory."""
        import amp.plugins as pkg

        for _, module_name, _ in pkgutil.iter_modules(pkg.__path__):
            if module_name in ("base", "registry"):
                continue
            try:
                module = importlib.import_module(f"amp.plugins.{module_name}")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BasePlugin)
                        and attr is not BasePlugin
                    ):
                        instance = attr()
                        self.register(instance)
            except Exception as e:
                print(f"[PluginRegistry] Failed to load plugin {module_name}: {e}")

    def get_enabled(self, user_config: dict) -> list[BasePlugin]:
        """Get plugins enabled for this user."""
        user_plugins = user_config.get("plugins", {})
        result = []
        for name, plugin in self._plugins.items():
            if user_plugins.get(name, plugin.enabled_by_default):
                result.append(plugin)
        return result

    def get(self, name: str) -> BasePlugin | None:
        return self._plugins.get(name)

    def all(self) -> list[BasePlugin]:
        return list(self._plugins.values())


_registry = PluginRegistry()
