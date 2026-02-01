# celine/dt/core/broker/registry.py
"""
Registry and configuration loading for brokers.

Follows the same pattern as clients registry, allowing brokers to be
configured via YAML and dynamically loaded at startup.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator
from xmlrpc.client import boolean

from celine.dt.contracts.broker import Broker
from celine.dt.core.loader import import_attr, load_yaml_files, substitute_env_vars
from celine.dt.core.auth.provider import TokenProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrokerSpec:
    """
    Specification for a broker instance.

    Attributes:
        name: Unique identifier for this broker.
        class_path: Import path in format 'module:ClassName'.
        enabled: Whether this broker is enabled.
        config: Configuration dict passed to broker constructor.
    """

    name: str
    class_path: str
    enabled: bool = True
    jwt_auth: bool = False
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokersConfig:
    """
    Container for all broker specifications.

    Attributes:
        brokers: List of broker specifications.
        default_broker: Name of the default broker to use.
    """

    brokers: list[BrokerSpec] = field(default_factory=list)
    default_broker: str | None = None


class BrokerRegistry:
    """
    Registry for broker instances.

    Provides named access to broker instances for use by DT apps
    and the broker service.
    """

    def __init__(self) -> None:
        self._brokers: dict[str, Broker] = {}
        self._default: str | None = None

    def register(self, name: str, broker: Broker) -> None:
        """
        Register a broker instance.

        Args:
            name: Unique identifier for the broker.
            broker: Broker instance.

        Raises:
            ValueError: If a broker with this name already exists.
        """
        if name in self._brokers:
            raise ValueError(f"Broker '{name}' is already registered")

        self._brokers[name] = broker
        logger.info("Registered broker: %s", name)

    def set_default(self, name: str) -> None:
        """
        Set the default broker.

        Args:
            name: Name of the broker to use as default.

        Raises:
            KeyError: If broker doesn't exist.
        """
        if name not in self._brokers:
            raise KeyError(f"Broker '{name}' not found in registry")

        self._default = name
        logger.info("Set default broker: %s", name)

    def get(self, name: str | None = None) -> Broker:
        """
        Get a broker by name or the default broker.

        Args:
            name: Broker name, or None for default.

        Returns:
            The broker instance.

        Raises:
            KeyError: If broker not found or no default set.
        """
        if name is None:
            if self._default is None:
                raise KeyError("No default broker configured")
            name = self._default

        if name not in self._brokers:
            raise KeyError(f"Broker '{name}' not found in registry")

        return self._brokers[name]

    def has(self, name: str) -> bool:
        """Check if a broker is registered."""
        return name in self._brokers

    def list(self) -> list[str]:
        """List all registered broker names."""
        return list(self._brokers.keys())

    def items(self) -> Iterator[tuple[str, Broker]]:
        """Iterate over (name, broker) pairs."""
        yield from self._brokers.items()

    @property
    def default_name(self) -> str | None:
        """Get the default broker name."""
        return self._default

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __len__(self) -> int:
        return len(self._brokers)


def load_brokers_config(patterns: Iterable[str]) -> BrokersConfig:
    """
    Load brokers configuration from YAML files.

    Expected YAML structure:
    ```yaml
    brokers:
      mqtt_local:
        class: celine.dt.core.broker.mqtt:MqttBroker
        enabled: true
        config:
          host: "${MQTT_HOST:-localhost}"
          port: 1883
          topic_prefix: "celine/dt/"

    default_broker: mqtt_local
    ```

    Args:
        patterns: Glob patterns for YAML config files.

    Returns:
        BrokersConfig with all broker specifications.

    Raises:
        ValueError: If configuration is invalid.
    """
    yamls = load_yaml_files(patterns)

    brokers_map: dict[str, dict[str, Any]] = {}
    default_broker: str | None = None

    for data in yamls:
        # Process brokers section
        for name, spec in data.get("brokers", {}).items():
            brokers_map[name] = spec

        # Check for default broker setting
        if "default_broker" in data:
            default_broker = data["default_broker"]

    specs: list[BrokerSpec] = []

    for name, raw in brokers_map.items():
        if "class" not in raw:
            raise ValueError(f"Broker '{name}' missing required 'class' field")

        # Substitute environment variables in config
        config = substitute_env_vars(raw.get("config", {}))

        spec = BrokerSpec(
            name=name,
            class_path=raw["class"],
            jwt_auth=raw.get("jwt_auth", False),
            enabled=raw.get("enabled", True),
            config=config,
        )
        specs.append(spec)

    logger.info(
        "Loaded %d broker spec(s): %s",
        len(specs),
        [s.name for s in specs],
    )

    return BrokersConfig(brokers=specs, default_broker=default_broker)


def load_and_register_brokers(
    cfg: BrokersConfig, token_provider: TokenProvider | None = None
) -> BrokerRegistry:
    """
    Load broker classes and instantiate them.

    Args:
        cfg: Brokers configuration.

    Returns:
        BrokerRegistry with all brokers registered.

    Raises:
        ImportError: If a broker class cannot be imported.
        TypeError: If broker instantiation fails.
    """
    registry = BrokerRegistry()

    for spec in cfg.brokers:
        if not spec.enabled:
            logger.info("Skipping disabled broker: %s", spec.name)
            continue

        logger.info("Loading broker '%s' from '%s'", spec.name, spec.class_path)

        try:
            broker_class = import_attr(spec.class_path)
        except (ImportError, AttributeError) as exc:
            logger.error("Failed to import broker class '%s'", spec.class_path)
            raise

        try:

            if spec.jwt_auth:
                logger.info(f"Token login enabled for broker '{spec.name}'")

            broker_instance = broker_class(
                **spec.config,
                token_provider=token_provider if spec.jwt_auth else None,
            )
        except TypeError as exc:
            logger.error(
                "Failed to instantiate broker '%s' with config: %s",
                spec.name,
                exc,
            )
            raise TypeError(
                f"Failed to instantiate broker '{spec.name}': {exc}"
            ) from exc

        registry.register(spec.name, broker_instance)

    # Set default broker if configured
    if cfg.default_broker and registry.has(cfg.default_broker):
        registry.set_default(cfg.default_broker)
    elif len(registry) == 1:
        # Auto-set default if only one broker
        registry.set_default(registry.list()[0])

    logger.info(
        "Successfully loaded %d broker(s): %s (default: %s)",
        len(registry),
        registry.list(),
        registry.default_name,
    )

    return registry
