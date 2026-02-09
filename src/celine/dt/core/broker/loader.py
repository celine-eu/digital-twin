# celine/dt/core/broker/loader.py
"""
Broker loader – reads config/brokers.yaml, creates SDK MqttBroker instances
with optional OIDC token-based authentication.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from celine.sdk.auth import TokenProvider
from celine.sdk.broker import MqttBroker, MqttConfig

from celine.dt.core.broker.service import BrokerService
from celine.dt.core.loader import load_yaml_files, substitute_env_vars

logger = logging.getLogger(__name__)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _coerce_int(value: Any) -> int:
    return int(value)


def _coerce_float(value: Any) -> float:
    return float(value)


def load_and_register_brokers(
    *,
    patterns: Iterable[str],
    service: BrokerService,
    token_provider: TokenProvider | None = None,
) -> None:
    """Load broker definitions from YAML and register SDK broker instances.

    Expected YAML::

        brokers:
          celine_mqtt:
            enabled: true
            config:
              host: "${MQTT_HOST:-localhost}"
              port: ${MQTT_PORT:-1883}
              topic_prefix: "celine/dt/"
              use_tls: false
              # Static credentials (used when no token_provider):
              # username: "..."
              # password: "..."

        default_broker: celine_mqtt

    When a ``token_provider`` is supplied, it is injected into every
    ``MqttBroker`` — the broker will use JWT-based auth with automatic
    token refresh instead of static username/password.
    """
    yamls = load_yaml_files(patterns)
    if not yamls:
        logger.debug("No broker config files matched: %s", list(patterns))
        return

    for data in yamls:
        for name, spec in (data.get("brokers") or {}).items():
            enabled = _coerce_bool(substitute_env_vars(spec.get("enabled", True)))
            if not enabled:
                logger.info("Skipping disabled broker '%s'", name)
                continue

            raw_config = substitute_env_vars(spec.get("config", {}))

            auth_with_token = _coerce_bool(
                substitute_env_vars(spec.get("auth_with_token", False))
            )
            # Only inject token provider when explicitly requested
            effective_token_provider = token_provider if auth_with_token else None

            # Build MqttConfig from YAML
            mqtt_kwargs: dict[str, Any] = {}
            field_coercions = {
                "port": _coerce_int,
                "keepalive": _coerce_int,
                "max_reconnect_attempts": _coerce_int,
                "use_tls": _coerce_bool,
                "clean_session": _coerce_bool,
                "reconnect_interval": _coerce_float,
                "token_refresh_margin": _coerce_float,
            }

            for key, value in raw_config.items():
                if key in field_coercions:
                    mqtt_kwargs[key] = field_coercions[key](value)
                else:
                    mqtt_kwargs[key] = value

            config = MqttConfig(**mqtt_kwargs)

            # Create broker with optional token provider
            broker = MqttBroker(config=config, token_provider=effective_token_provider)

            service.register(name, broker)
            logger.info(
                "Loaded broker '%s' (host=%s:%d, tls=%s, jwt_auth=%s)",
                name,
                config.host,
                config.port,
                config.use_tls,
                token_provider is not None,
            )

        # Set default
        default_name = data.get("default_broker")
        if default_name:
            try:
                service.set_default(default_name)
                logger.info("Default broker set to '%s'", default_name)
            except KeyError:
                logger.warning(
                    "default_broker '%s' not found in registered brokers",
                    default_name,
                )

    logger.info(
        "Broker loading complete: %d broker(s) registered", len(service._brokers)
    )
