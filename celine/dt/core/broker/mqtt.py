# celine/dt/core/broker/mqtt.py
"""
MQTT broker implementation for Digital Twin event publishing.

This module provides a concrete Broker implementation using MQTT protocol,
suitable for IoT and edge computing scenarios where MQTT is the standard.

Usage:
    broker = MqttBroker(
        host="localhost",
        port=1883,
        client_id="dt-instance-1",
    )
    
    async with broker:
        result = await broker.publish(BrokerMessage(
            topic="dt/ev-charging/rec-folgaria/readiness",
            payload={"indicator": "OPTIMAL", ...},
        ))
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from celine.dt.contracts.broker import (
    BrokerBase,
    BrokerMessage,
    PublishResult,
    QoS,
)

logger = logging.getLogger(__name__)

# Try to import aiomqtt (paho-mqtt async wrapper)
AIOMQTT_AVAILABLE = False
try:
    import aiomqtt
    AIOMQTT_AVAILABLE = True
except ImportError:
    aiomqtt = None  # type: ignore[assignment]
    logger.warning(
        "aiomqtt not installed. MQTT broker will not be available. "
        "Install with: pip install aiomqtt"
    )


@dataclass
class MqttConfig:
    """
    Configuration for MQTT broker connection.
    
    Attributes:
        host: MQTT broker hostname.
        port: MQTT broker port (default 1883, or 8883 for TLS).
        client_id: Unique client identifier. Auto-generated if not provided.
        username: Optional authentication username.
        password: Optional authentication password.
        use_tls: Whether to use TLS encryption.
        ca_certs: Path to CA certificate file for TLS.
        certfile: Path to client certificate for mutual TLS.
        keyfile: Path to client private key for mutual TLS.
        keepalive: Keepalive interval in seconds.
        clean_session: Whether to start with a clean session.
        reconnect_interval: Seconds between reconnection attempts.
        max_reconnect_attempts: Maximum reconnection attempts (0 = infinite).
        topic_prefix: Optional prefix for all topics.
    """
    
    host: str = "localhost"
    port: int = 1883
    client_id: str | None = None
    username: str | None = None
    password: str | None = None
    use_tls: bool = False
    ca_certs: str | None = None
    certfile: str | None = None
    keyfile: str | None = None
    keepalive: int = 60
    clean_session: bool = True
    reconnect_interval: float = 5.0
    max_reconnect_attempts: int = 0
    topic_prefix: str = ""
    
    def __post_init__(self):
        if self.client_id is None:
            self.client_id = f"celine-dt-{uuid4().hex[:8]}"


class MqttBroker(BrokerBase):
    """
    MQTT broker implementation using aiomqtt.
    
    Features:
    - Automatic reconnection handling
    - TLS/SSL support
    - QoS level support
    - Message retention
    - JSON payload serialization
    - Topic prefixing
    
    Example:
        config = MqttConfig(
            host="mosquitto.local",
            port=1883,
            topic_prefix="celine/dt/",
        )
        
        broker = MqttBroker(config)
        await broker.connect()
        
        result = await broker.publish(BrokerMessage(
            topic="events/readiness",
            payload=event.model_dump(),
        ))
        
        await broker.disconnect()
    """
    
    def __init__(self, config: MqttConfig | None = None, **kwargs):
        """
        Initialize MQTT broker.
        
        Args:
            config: MqttConfig instance, or None to use defaults.
            **kwargs: Override config fields (for convenience).
        """
        if not AIOMQTT_AVAILABLE:
            raise ImportError(
                "aiomqtt is required for MQTT broker. "
                "Install with: pip install aiomqtt"
            )
        
        if config is None:
            config = MqttConfig(**kwargs)
        else:
            # Allow kwargs to override config
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
        
        self._config = config
        self._client: aiomqtt.Client | None = None
        self._connected = False
        self._lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task | None = None
    
    @property
    def config(self) -> MqttConfig:
        """Get the broker configuration."""
        return self._config
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to the broker."""
        return self._connected and self._client is not None
    
    def _build_tls_context(self) -> ssl.SSLContext | None:
        """Build SSL context if TLS is enabled."""
        if not self._config.use_tls:
            return None
        
        context = ssl.create_default_context()
        
        if self._config.ca_certs:
            context.load_verify_locations(self._config.ca_certs)
        
        if self._config.certfile and self._config.keyfile:
            context.load_cert_chain(
                certfile=self._config.certfile,
                keyfile=self._config.keyfile,
            )
        
        return context
    
    def _full_topic(self, topic: str) -> str:
        """Apply topic prefix if configured."""
        if self._config.topic_prefix:
            prefix = self._config.topic_prefix.rstrip("/")
            return f"{prefix}/{topic.lstrip('/')}"
        return topic
    
    async def connect(self) -> None:
        """
        Connect to the MQTT broker.
        
        This method is idempotent - calling it when already connected is safe.
        """
        async with self._lock:
            if self._connected:
                logger.debug("Already connected to MQTT broker")
                return
            
            logger.info(
                "Connecting to MQTT broker at %s:%d",
                self._config.host,
                self._config.port,
            )
            
            tls_context = self._build_tls_context()
            
            self._client = aiomqtt.Client(
                hostname=self._config.host,
                port=self._config.port,
                identifier=self._config.client_id,
                username=self._config.username,
                password=self._config.password,
                tls_context=tls_context,
                keepalive=self._config.keepalive,
                clean_session=self._config.clean_session,
            )
            
            try:
                await self._client.__aenter__()
                self._connected = True
                logger.info(
                    "Connected to MQTT broker %s:%d as %s",
                    self._config.host,
                    self._config.port,
                    self._config.client_id,
                )
            except Exception as exc:
                logger.error("Failed to connect to MQTT broker: %s", exc)
                self._client = None
                raise
    
    async def disconnect(self) -> None:
        """
        Disconnect from the MQTT broker.
        
        Gracefully closes the connection after flushing pending messages.
        """
        async with self._lock:
            if self._reconnect_task:
                self._reconnect_task.cancel()
                self._reconnect_task = None
            
            if self._client is not None:
                try:
                    await self._client.__aexit__(None, None, None)
                    logger.info("Disconnected from MQTT broker")
                except Exception as exc:
                    logger.warning("Error during MQTT disconnect: %s", exc)
                finally:
                    self._client = None
                    self._connected = False
    
    async def publish(self, message: BrokerMessage) -> PublishResult:
        """
        Publish a message to the MQTT broker.
        
        Args:
            message: The message to publish.
            
        Returns:
            PublishResult indicating success or failure.
        """
        if not self.is_connected:
            return PublishResult(
                success=False,
                error="Not connected to MQTT broker",
            )
        
        topic = self._full_topic(message.topic)
        
        # Prepare payload
        payload_dict = dict(message.payload)
        
        # Add timestamp if not present
        if message.timestamp:
            payload_dict.setdefault("_timestamp", message.timestamp.isoformat())
        else:
            payload_dict.setdefault(
                "_timestamp",
                datetime.now(timezone.utc).isoformat(),
            )
        
        # Add correlation ID if present
        if message.correlation_id:
            payload_dict.setdefault("_correlationId", message.correlation_id)
        
        try:
            payload_bytes = json.dumps(payload_dict, default=str).encode("utf-8")
        except (TypeError, ValueError) as exc:
            return PublishResult(
                success=False,
                error=f"Failed to serialize payload: {exc}",
            )
        
        try:
            await self._client.publish(
                topic=topic,
                payload=payload_bytes,
                qos=message.qos.value,
                retain=message.retain,
            )
            
            message_id = str(uuid4())
            
            logger.debug(
                "Published message to %s (qos=%d, retain=%s, size=%d bytes)",
                topic,
                message.qos.value,
                message.retain,
                len(payload_bytes),
            )
            
            return PublishResult(
                success=True,
                message_id=message_id,
            )
            
        except Exception as exc:
            logger.error("Failed to publish to %s: %s", topic, exc)
            return PublishResult(
                success=False,
                error=str(exc),
            )
    
    async def publish_event(
        self,
        event: Any,
        topic: str | None = None,
        qos: QoS = QoS.AT_LEAST_ONCE,
        retain: bool = False,
    ) -> PublishResult:
        """
        Convenience method to publish a Pydantic event model.
        
        Args:
            event: A Pydantic model (e.g., DTEvent subclass).
            topic: Override topic. If None, derives from event type.
            qos: Quality of Service level.
            retain: Whether to retain the message.
            
        Returns:
            PublishResult indicating success or failure.
        """
        # Try to get topic from event if not provided
        if topic is None:
            # Convention: dt/{module}/{entity_id}/{event_type}
            event_type = getattr(event, "type", None)
            if event_type and hasattr(event, "payload"):
                payload = event.payload
                community_id = getattr(payload, "community_id", "unknown")
                # e.g., "dt.ev-charging.readiness-computed" -> "ev-charging/readiness-computed"
                type_parts = event_type.replace("dt.", "").replace(".", "/")
                topic = f"dt/{type_parts}/{community_id}"
            else:
                topic = "dt/events/unknown"
        
        # Serialize event
        if hasattr(event, "model_dump"):
            payload = event.model_dump(mode="json", by_alias=True)
        elif hasattr(event, "dict"):
            payload = event.dict(by_alias=True)
        else:
            payload = dict(event)
        
        message = BrokerMessage(
            topic=topic,
            payload=payload,
            qos=qos,
            retain=retain,
            correlation_id=getattr(event, "correlation_id", None),
            timestamp=getattr(event, "timestamp", None),
        )
        
        return await self.publish(message)


# =============================================================================
# Factory Function
# =============================================================================

def create_mqtt_broker(
    host: str = "localhost",
    port: int = 1883,
    username: str | None = None,
    password: str | None = None,
    use_tls: bool = False,
    topic_prefix: str = "",
    **kwargs,
) -> MqttBroker:
    """
    Factory function to create an MQTT broker instance.
    
    Args:
        host: MQTT broker hostname.
        port: MQTT broker port.
        username: Optional authentication username.
        password: Optional authentication password.
        use_tls: Whether to use TLS.
        topic_prefix: Prefix for all topics.
        **kwargs: Additional MqttConfig fields.
        
    Returns:
        Configured MqttBroker instance.
    """
    config = MqttConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
        topic_prefix=topic_prefix,
        **kwargs,
    )
    return MqttBroker(config)
