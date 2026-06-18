"""Service registry - simple plugin discovery for the monorepo.

Instead of Python entry_points (overkill for a monorepo), we use a dict-based
registry. Adding a new implementation = one line in the relevant __init__.py.

Usage:
    from job_agent_services.registry import ServiceRegistry

    # Register (done once at import time in each service module)
    ServiceRegistry.register("llm", "ollama", OllamaProvider)

    # Resolve (done in container.py)
    provider_cls = ServiceRegistry.get("llm", "ollama")
    provider = provider_cls(**settings)
"""

from typing import Any


class ServiceRegistry:
    """Central registry for all service implementations."""

    _registry: dict[str, dict[str, type]] = {}

    @classmethod
    def register(cls, category: str, name: str, implementation: type) -> None:
        """Register a service implementation.

        Args:
            category: Service category (e.g., "llm", "vector_store", "browser")
            name: Implementation name (e.g., "ollama", "openai", "chroma")
            implementation: The concrete class
        """
        if category not in cls._registry:
            cls._registry[category] = {}
        cls._registry[category][name] = implementation

    @classmethod
    def get(cls, category: str, name: str) -> type:
        """Get a registered implementation class.

        Raises KeyError if not found.
        """
        if category not in cls._registry:
            raise KeyError(f"No services registered for category '{category}'")
        if name not in cls._registry[category]:
            available = list(cls._registry[category].keys())
            raise KeyError(
                f"No '{name}' implementation in category '{category}'. "
                f"Available: {available}"
            )
        return cls._registry[category][name]

    @classmethod
    def list_category(cls, category: str) -> list[str]:
        """List all registered implementations for a category."""
        return list(cls._registry.get(category, {}).keys())

    @classmethod
    def list_categories(cls) -> list[str]:
        """List all registered categories."""
        return list(cls._registry.keys())

    @classmethod
    def create(cls, category: str, name: str, **kwargs: Any) -> Any:
        """Create an instance of a registered service.

        Shortcut for `ServiceRegistry.get(category, name)(**kwargs)`.
        """
        impl_cls = cls.get(category, name)
        return impl_cls(**kwargs)
