# celine/dt/core/broker/__init__.py
"""
Broker infrastructure for Digital Twin event publishing.

This module provides:
- Abstract Broker protocol for message publishing
- Concrete MQTT implementation for local/IoT scenarios
- Configuration and factory utilities

Example usage:

    from celine.dt.core.broker import create_mqtt_broker, BrokerMessage, QoS

    # Create broker instance
    broker = create_mqtt_broker(
        host="localhost",
        port=1883,
        topic_prefix="celine/dt/",
    )

    # Use as async context manager
    async with broker:
        result = await broker.publish(BrokerMessage(
            topic="events/readiness",
            payload={"indicator": "OPTIMAL"},
            qos=QoS.AT_LEAST_ONCE,
        ))

        if result.success:
            print(f"Published: {result.message_id}")
"""

from celine.dt.contracts.broker import (
    Broker,
    BrokerBase,
    BrokerMessage,
    PublishResult,
    QoS,
)

from celine.dt.core.broker.mqtt import (
    MqttBroker,
    MqttConfig,
    create_mqtt_broker,
)

from celine.dt.core.broker.registry import (
    BrokerRegistry,
    load_and_register_brokers,
    load_brokers_config,
    BrokerSpec,
    BrokersConfig,
)

from celine.dt.core.broker.service import BrokerService

__all__ = [
    # Protocol & base
    "Broker",
    "BrokerBase",
    "BrokerMessage",
    "PublishResult",
    "QoS",
    # MQTT implementation
    "MqttBroker",
    "MqttConfig",
    "create_mqtt_broker",
    # Registry & config
    "BrokerRegistry",
    "load_and_register_brokers",
    "load_brokers_config",
    "BrokerSpec",
    "BrokersConfig",
    # Service
    "BrokerService",
]
