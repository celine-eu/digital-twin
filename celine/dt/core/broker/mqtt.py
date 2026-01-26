# celine/dt/core/broker/mqtt.py
"""
MQTT broker implementation for Digital Twin event publishing and subscription.

This module provides a concrete Broker implementation using MQTT protocol,
suitable for IoT and edge computing scenarios where MQTT is the standard.

Usage:
    broker = MqttBroker(
        host="localhost",
        port=1883,
        client_id="dt-instance-1",
    )

    async with broker:
        # Publish
        result = await broker.publish(BrokerMessage(
            topic="dt/events/readiness",
            payload={"indicator": "OPTIMAL"},
        ))

        # Subscribe
        async def handle_message(msg: ReceivedMessage):
            print(f"Received on {msg.topic}: {msg.payload}")

        sub = await broker.subscribe(
            topics=["dt/alerts/#"],
            handler=handle_message,
        )

        # Later...
        await broker.unsubscribe(sub.subscription_id)
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from celine.dt.contracts.broker import (
    BrokerBase,
    BrokerMessage,
    MessageHandler,
    PublishResult,
    QoS,
    ReceivedMessage,
    SubscribeResult,
)

logger = logging.getLogger(__name__)

import aiomqtt


# =============================================================================
# Token Provider Protocol (to avoid circular imports)
# =============================================================================


@runtime_checkable
class TokenProviderProtocol(Protocol):
    """Protocol for token providers to avoid circular imports."""

    async def get_token(self) -> Any:
        """Return a valid access token with access_token and expires_at attrs."""
        ...


# =============================================================================
# Configuration
# =============================================================================


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
        token_refresh_margin: Seconds before token expiry to trigger refresh.
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
    token_refresh_margin: float = 30.0

    def __post_init__(self):
        if self.client_id is None:
            self.client_id = f"celine-dt-{uuid4().hex[:8]}"


# =============================================================================
# Internal Subscription Tracking
# =============================================================================


@dataclass
class _Subscription:
    """Internal subscription tracking."""

    id: str
    topics: list[str]
    handler: MessageHandler
    qos: QoS


# =============================================================================
# MQTT Broker Implementation
# =============================================================================


class MqttBroker(BrokerBase):
    """
    MQTT broker implementation using aiomqtt.

    Features:
    - Publish messages to topics
    - Subscribe to topics with wildcard support
    - Automatic reconnection handling
    - TLS/SSL support
    - QoS level support
    - Message retention
    - JSON payload serialization
    - Topic prefixing
    - JWT authentication via TokenProvider with automatic refresh

    Example:
        from celine.dt.core.broker import MqttBroker, MqttConfig, BrokerMessage

        broker = MqttBroker(MqttConfig(host="localhost"))

        async with broker:
            # Publish
            await broker.publish(BrokerMessage(
                topic="events/test",
                payload={"value": 42},
            ))

            # Subscribe
            async def on_message(msg):
                print(f"{msg.topic}: {msg.payload}")

            result = await broker.subscribe(["events/#"], on_message)

            # Keep running to receive messages...
            await asyncio.sleep(60)

            await broker.unsubscribe(result.subscription_id)
    """

    def __init__(
        self,
        config: MqttConfig | None = None,
        token_provider: TokenProviderProtocol | None = None,
        **kwargs,
    ):
        """
        Initialize MQTT broker.

        Args:
            config: MqttConfig instance, or None to use defaults.
            token_provider: Optional TokenProvider for JWT authentication.
            **kwargs: Override config fields (for convenience).
        """
        if config is None:
            config = MqttConfig(**kwargs)
        else:
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        self._config = config
        self._token_provider = token_provider

        # Connection state
        self._client: aiomqtt.Client | None = None
        self._connected = False
        self._lock = asyncio.Lock()

        # Subscription state
        self._subscriptions: dict[str, _Subscription] = {}
        self._listener_task: asyncio.Task | None = None

        # Token refresh
        self._token_refresh_task: asyncio.Task | None = None

        # Stats
        self._publish_count = 0
        self._receive_count = 0
        self._error_count = 0

    @property
    def config(self) -> MqttConfig:
        """Get the broker configuration."""
        return self._config

    @property
    def token_provider(self) -> TokenProviderProtocol | None:
        """Get the token provider if configured."""
        return self._token_provider

    @property
    def is_connected(self) -> bool:
        """Check if connected to the broker."""
        return self._connected and self._client is not None

    @property
    def subscription_count(self) -> int:
        """Number of active subscriptions."""
        return len(self._subscriptions)

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

    async def _get_credentials(self) -> tuple[str | None, str | None]:
        """Get authentication credentials, using token provider if configured."""
        if self._token_provider:
            token = await self._token_provider.get_token()
            self._schedule_token_refresh(token.expires_at)
            return "jwt", token.access_token
        return self._config.username, self._config.password

    def _schedule_token_refresh(self, expires_at: float) -> None:
        """Schedule token refresh before expiry."""
        if self._token_refresh_task and not self._token_refresh_task.done():
            self._token_refresh_task.cancel()

        refresh_in = max(
            0, expires_at - time.time() - self._config.token_refresh_margin
        )

        logger.debug("Scheduling token refresh in %.1f seconds", refresh_in)

        self._token_refresh_task = asyncio.create_task(
            self._refresh_token_and_reconnect(refresh_in),
            name="mqtt-broker-token-refresh",
        )

    async def _refresh_token_and_reconnect(self, delay: float) -> None:
        """Wait for delay, then refresh token and reconnect."""
        try:
            await asyncio.sleep(delay)

            if not self._connected:
                return

            logger.info("Token expiring, reconnecting with fresh credentials")

            # Store current subscriptions
            subs = list(self._subscriptions.values())

            # Reconnect
            await self._disconnect_internal()
            await self._connect_internal()

            # Resubscribe
            if subs and self._client:
                for sub in subs:
                    for topic in sub.topics:
                        full_topic = self._full_topic(topic)
                        await self._client.subscribe(full_topic, qos=sub.qos.value)

                # Restart listener if we have subscriptions
                self._start_listener()

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Error during token refresh: %s", exc)

    async def _connect_internal(self) -> None:
        """Internal connect without lock."""
        logger.info(
            "Connecting to MQTT broker at %s:%d",
            self._config.host,
            self._config.port,
        )

        username, password = await self._get_credentials()
        tls_context = self._build_tls_context()

        self._client = aiomqtt.Client(
            hostname=self._config.host,
            port=self._config.port,
            identifier=self._config.client_id,
            username=username,
            password=password,
            tls_context=tls_context,
            keepalive=self._config.keepalive,
            clean_session=self._config.clean_session,
        )

        try:
            await self._client.__aenter__()
            self._connected = True
            logger.info(
                "Connected to MQTT broker %s:%d as %s%s",
                self._config.host,
                self._config.port,
                self._config.client_id,
                " (JWT auth)" if self._token_provider else "",
            )
        except Exception as exc:
            logger.error("Failed to connect to MQTT broker: %s", exc)
            self._client = None
            raise

    async def _disconnect_internal(self) -> None:
        """Internal disconnect without lock."""
        # Stop listener
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning("Error during MQTT disconnect: %s", exc)
            finally:
                self._client = None
                self._connected = False

    async def connect(self) -> None:
        """
        Connect to the MQTT broker.

        This method is idempotent - calling it when already connected is safe.
        """
        async with self._lock:
            if self._connected:
                logger.debug("Already connected to MQTT broker")
                return
            await self._connect_internal()

    async def disconnect(self) -> None:
        """
        Disconnect from the MQTT broker.

        Gracefully closes the connection and cancels all subscriptions.
        """
        async with self._lock:
            # Cancel token refresh
            if self._token_refresh_task:
                self._token_refresh_task.cancel()
                try:
                    await self._token_refresh_task
                except asyncio.CancelledError:
                    pass
                self._token_refresh_task = None

            # Clear subscriptions
            self._subscriptions.clear()

            await self._disconnect_internal()
            logger.info("Disconnected from MQTT broker")

    async def publish(self, message: BrokerMessage) -> PublishResult:
        """
        Publish a message to the MQTT broker.

        Args:
            message: The message to publish.

        Returns:
            PublishResult indicating success or failure.
        """
        if not self.is_connected or self._client is None:
            return PublishResult(
                success=False,
                error="Not connected to MQTT broker",
            )

        topic = self._full_topic(message.topic)

        # Prepare payload
        payload_dict = dict(message.payload)

        if message.timestamp:
            payload_dict.setdefault("_timestamp", message.timestamp.isoformat())
        else:
            payload_dict.setdefault(
                "_timestamp",
                datetime.now(timezone.utc).isoformat(),
            )

        if message.correlation_id:
            payload_dict.setdefault("_correlationId", message.correlation_id)

        try:
            payload_bytes = json.dumps(payload_dict, default=str).encode("utf-8")
        except (TypeError, ValueError) as exc:
            return PublishResult(success=False, error=f"Failed to serialize: {exc}")

        try:
            await self._client.publish(
                topic=topic,
                payload=payload_bytes,
                qos=message.qos.value,
                retain=message.retain,
            )

            self._publish_count += 1
            message_id = str(uuid4())

            logger.debug(
                "Published to %s (qos=%d, size=%d bytes)",
                topic,
                message.qos.value,
                len(payload_bytes),
            )

            return PublishResult(success=True, message_id=message_id)

        except Exception as exc:
            self._error_count += 1
            logger.error("Failed to publish to %s: %s", topic, exc)
            return PublishResult(success=False, error=str(exc))

    async def subscribe(
        self,
        topics: list[str],
        handler: MessageHandler,
        qos: QoS = QoS.AT_LEAST_ONCE,
    ) -> SubscribeResult:
        """
        Subscribe to topics and register a message handler.

        Args:
            topics: List of topic patterns (supports + and # wildcards).
            handler: Async callback invoked for each received message.
            qos: Quality of Service level for the subscription.

        Returns:
            SubscribeResult with subscription_id for later unsubscribe.
        """
        if not self.is_connected or self._client is None:
            return SubscribeResult(
                success=False,
                error="Not connected to MQTT broker",
            )

        subscription_id = f"sub-{uuid4().hex[:8]}"

        try:
            # Subscribe to each topic
            for topic in topics:
                full_topic = self._full_topic(topic)
                await self._client.subscribe(full_topic, qos=qos.value)
                logger.info("Subscribed to: %s", full_topic)

            # Track subscription
            self._subscriptions[subscription_id] = _Subscription(
                id=subscription_id,
                topics=topics,
                handler=handler,
                qos=qos,
            )

            # Start listener if not running
            self._start_listener()

            return SubscribeResult(success=True, subscription_id=subscription_id)

        except Exception as exc:
            self._error_count += 1
            logger.error("Failed to subscribe: %s", exc)
            return SubscribeResult(success=False, error=str(exc))

    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from a previous subscription.

        Args:
            subscription_id: The ID returned from subscribe().

        Returns:
            True if unsubscribed successfully, False if not found.
        """
        sub = self._subscriptions.pop(subscription_id, None)
        if sub is None:
            return False

        # Note: We don't unsubscribe from MQTT topics because other
        # subscriptions might use the same topics. The handler just
        # won't be called anymore.

        logger.info("Unsubscribed: %s", subscription_id)

        # Stop listener if no more subscriptions
        if not self._subscriptions and self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        return True

    def _start_listener(self) -> None:
        """Start the message listener task if not running."""
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.create_task(
                self._listen_loop(),
                name="mqtt-broker-listener",
            )

    async def _listen_loop(self) -> None:
        """Listen for incoming messages and dispatch to handlers."""
        if self._client is None:
            return

        try:
            async for message in self._client.messages:
                if not self._connected:
                    break

                await self._dispatch_message(message)

        except asyncio.CancelledError:
            logger.debug("Listener loop cancelled")
            raise
        except Exception as exc:
            logger.error("Listener error: %s", exc)
            self._error_count += 1

    async def _dispatch_message(self, message: aiomqtt.Message) -> None:
        """Dispatch a received message to matching handlers."""
        self._receive_count += 1

        topic = str(message.topic)
        raw_payload = message.payload if isinstance(message.payload, bytes) else b""

        # Parse payload
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"_raw": raw_payload.decode("utf-8", errors="replace")}

        received = ReceivedMessage(
            topic=topic,
            payload=payload,
            raw_payload=raw_payload,
            qos=QoS(message.qos) if message.qos in (0, 1, 2) else QoS.AT_LEAST_ONCE,
            timestamp=datetime.now(timezone.utc),
        )

        # Find matching subscriptions
        for sub in self._subscriptions.values():
            if self._topic_matches(topic, sub.topics):
                try:
                    await sub.handler(received)
                except Exception as exc:
                    self._error_count += 1
                    logger.error(
                        "Handler error for subscription %s: %s",
                        sub.id,
                        exc,
                    )

    def _topic_matches(self, topic: str, patterns: list[str]) -> bool:
        """Check if a topic matches any of the subscription patterns."""
        for pattern in patterns:
            full_pattern = self._full_topic(pattern)
            if self._topic_matches_pattern(topic, full_pattern):
                return True
        return False

    @staticmethod
    def _topic_matches_pattern(topic: str, pattern: str) -> bool:
        """Check if a topic matches a single pattern with wildcards."""
        topic_parts = topic.split("/")
        pattern_parts = pattern.split("/")

        for i, pattern_part in enumerate(pattern_parts):
            if pattern_part == "#":
                return True  # # matches everything from here

            if i >= len(topic_parts):
                return False  # Topic is shorter than pattern

            if pattern_part == "+":
                continue  # + matches exactly one level

            if pattern_part != topic_parts[i]:
                return False  # Literal mismatch

        return len(topic_parts) == len(pattern_parts)

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
        if topic is None:
            event_type = getattr(event, "type", None)
            if event_type and hasattr(event, "payload"):
                payload = event.payload
                community_id = getattr(payload, "community_id", "unknown")
                type_parts = event_type.replace("dt.", "").replace(".", "/")
                topic = f"dt/{type_parts}/{community_id}"
            else:
                topic = "dt/events/unknown"

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

    def get_stats(self) -> dict[str, Any]:
        """Get broker statistics."""
        return {
            "connected": self.is_connected,
            "publish_count": self._publish_count,
            "receive_count": self._receive_count,
            "error_count": self._error_count,
            "subscription_count": len(self._subscriptions),
            "subscriptions": [
                {"id": s.id, "topics": s.topics} for s in self._subscriptions.values()
            ],
        }


# =============================================================================
# Factory Function
# =============================================================================


def create_mqtt_broker(
    host: str = "localhost",
    port: int = 1883,
    username: str | None = None,
    password: str | None = None,
    token_provider: TokenProviderProtocol | None = None,
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
        token_provider: Optional TokenProvider for JWT authentication.
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
    return MqttBroker(config, token_provider=token_provider)
