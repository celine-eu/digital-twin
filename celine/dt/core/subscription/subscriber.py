# celine/dt/core/broker/subscriber.py
"""
MQTT subscriber for receiving events from the broker.

This module provides the MqttSubscriber class which manages MQTT subscriptions,
handles incoming messages, and supports automatic token refresh for JWT authentication.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable
from uuid import uuid4

from celine.dt.contracts.broker import QoS
from celine.dt.core.broker.mqtt import MqttConfig

import aiomqtt

logger = logging.getLogger(__name__)


# Callback type for message handling
MessageCallback = Callable[[str, dict[str, Any], bytes], Awaitable[None]]


class MqttSubscriber:
    """
    MQTT subscriber with automatic reconnection and token refresh.

    Features:
    - Subscribe to multiple topics with wildcards
    - Automatic reconnection on disconnect
    - JWT token refresh before expiry
    - Concurrent message handling

    Example:
        subscriber = MqttSubscriber(
            config=MqttConfig(host="localhost", port=1883),
            token_provider=oidc_provider,
        )

        await subscriber.start(
            topics=["dt/ev-charging/#"],
            on_message=handle_message,
        )

        # Later...
        await subscriber.stop()
    """

    def __init__(
        self,
        config: MqttConfig,
        token_provider: Any | None = None,
        qos: QoS = QoS.AT_LEAST_ONCE,
    ) -> None:
        """
        Initialize the subscriber.

        Args:
            config: MQTT connection configuration.
            token_provider: Optional TokenProvider for JWT authentication.
            qos: Default QoS level for subscriptions.
        """

        self._config = config
        self._token_provider = token_provider
        self._qos = qos

        self._client: aiomqtt.Client | None = None
        self._topics: list[str] = []
        self._on_message: MessageCallback | None = None

        self._running = False
        self._listener_task: asyncio.Task | None = None
        self._token_refresh_task: asyncio.Task | None = None
        self._reconnect_event = asyncio.Event()

        self._message_count = 0
        self._error_count = 0
        self._last_message_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        """Check if the subscriber is running."""
        return self._running

    @property
    def message_count(self) -> int:
        """Total messages received."""
        return self._message_count

    @property
    def error_count(self) -> int:
        """Total processing errors."""
        return self._error_count

    @property
    def topics(self) -> list[str]:
        """Currently subscribed topics."""
        return list(self._topics)

    async def start(
        self,
        topics: list[str],
        on_message: MessageCallback,
    ) -> None:
        """
        Start the subscriber.

        Args:
            topics: List of topic patterns to subscribe to.
            on_message: Callback for received messages.
                Signature: async def on_message(topic: str, payload: dict, raw: bytes)
        """
        if self._running:
            logger.warning("Subscriber already running")
            return

        self._topics = list(topics)
        self._on_message = on_message
        self._running = True

        # Start the listener task
        self._listener_task = asyncio.create_task(
            self._listener_loop(),
            name="mqtt-subscriber-listener",
        )

        logger.info(
            "MQTT subscriber started for topics: %s",
            self._topics,
        )

    async def stop(self) -> None:
        """Stop the subscriber gracefully."""
        if not self._running:
            return

        logger.info("Stopping MQTT subscriber...")

        self._running = False

        # Cancel tasks
        if self._token_refresh_task:
            self._token_refresh_task.cancel()
            try:
                await self._token_refresh_task
            except asyncio.CancelledError:
                pass
            self._token_refresh_task = None

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        logger.info("MQTT subscriber stopped")

    async def add_topics(self, topics: list[str]) -> None:
        """
        Add topics to the subscription.

        Args:
            topics: Additional topic patterns to subscribe to.
        """
        new_topics = [t for t in topics if t not in self._topics]
        if not new_topics:
            return

        self._topics.extend(new_topics)

        # Trigger reconnect to apply new subscriptions
        if self._running:
            self._reconnect_event.set()

        logger.info("Added topics: %s", new_topics)

    async def remove_topics(self, topics: list[str]) -> None:
        """
        Remove topics from the subscription.

        Args:
            topics: Topic patterns to unsubscribe from.
        """
        for topic in topics:
            if topic in self._topics:
                self._topics.remove(topic)

        # Trigger reconnect to apply changes
        if self._running:
            self._reconnect_event.set()

        logger.info("Removed topics: %s", topics)

    async def _listener_loop(self) -> None:
        """
        Main listener loop with automatic reconnection.

        This loop maintains the MQTT connection and handles reconnection
        on failures or token refresh.
        """
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                logger.debug("Listener loop cancelled")
                break
            except Exception as exc:
                logger.error(
                    "MQTT connection error: %s, reconnecting in %ss",
                    exc,
                    self._config.reconnect_interval,
                )

                if self._running:
                    await asyncio.sleep(self._config.reconnect_interval)

    async def _connect_and_listen(self) -> None:
        """
        Connect to MQTT and listen for messages.

        Handles JWT authentication if token_provider is configured.
        """
        # Get credentials
        username = self._config.username
        password = self._config.password

        if self._token_provider:
            token = await self._token_provider.get_token()
            username = "jwt"  # Convention for JWT auth in Mosquitto
            password = token.access_token

            # Schedule token refresh
            self._schedule_token_refresh(token.expires_at)

        # Build TLS context if needed
        tls_context = None
        if self._config.use_tls:
            import ssl

            tls_context = ssl.create_default_context()
            if self._config.ca_certs:
                tls_context.load_verify_locations(self._config.ca_certs)
            if self._config.certfile and self._config.keyfile:
                tls_context.load_cert_chain(
                    certfile=self._config.certfile,
                    keyfile=self._config.keyfile,
                )

        # Connect
        async with aiomqtt.Client(
            hostname=self._config.host,
            port=self._config.port,
            identifier=f"{self._config.client_id}-sub",
            username=username,
            password=password,
            tls_context=tls_context,
            keepalive=self._config.keepalive,
            clean_session=self._config.clean_session,
        ) as client:
            logger.info(
                "Connected to MQTT broker %s:%d",
                self._config.host,
                self._config.port,
            )

            # Subscribe to all topics
            for topic in self._topics:
                full_topic = self._full_topic(topic)
                await client.subscribe(full_topic, qos=self._qos.value)
                logger.info("Subscribed to: %s", full_topic)

            # Clear reconnect event
            self._reconnect_event.clear()

            # Listen for messages
            async for message in client.messages:
                if not self._running:
                    break

                # Check for reconnect signal
                if self._reconnect_event.is_set():
                    logger.info("Reconnect requested, breaking listen loop")
                    break

                await self._handle_message(message)

    async def _handle_message(self, message: aiomqtt.Message) -> None:
        """
        Handle an incoming MQTT message.

        Parses JSON payload and invokes the callback.
        """
        self._message_count += 1
        self._last_message_at = datetime.now(timezone.utc)

        topic = str(message.topic)
        raw_payload = message.payload

        # Handle bytes or string payload
        if isinstance(raw_payload, bytes):
            payload_str = raw_payload.decode("utf-8")
        else:
            payload_str = str(raw_payload)
            raw_payload = payload_str.encode("utf-8")

        # Parse JSON
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as exc:
            self._error_count += 1
            logger.warning(
                "Invalid JSON payload on '%s': %s",
                topic,
                exc,
            )
            return

        # Strip topic prefix for callback
        clean_topic = self._strip_topic_prefix(topic)

        # Invoke callback
        if self._on_message:
            try:
                await self._on_message(clean_topic, payload, raw_payload)
            except Exception as exc:
                self._error_count += 1
                logger.error(
                    "Message callback error for '%s': %s",
                    topic,
                    exc,
                    exc_info=True,
                )

    def _schedule_token_refresh(self, expires_at: float) -> None:
        """
        Schedule a token refresh before expiry.

        Args:
            expires_at: Token expiry timestamp.
        """
        # Cancel existing task
        if self._token_refresh_task:
            self._token_refresh_task.cancel()

        # Calculate refresh time (80% of token lifetime)
        now = time.time()
        lifetime = expires_at - now
        refresh_delay = max(lifetime * 0.8, 60)  # At least 60 seconds

        self._token_refresh_task = asyncio.create_task(
            self._token_refresh_after(refresh_delay),
            name="mqtt-token-refresh",
        )

        logger.debug(
            "Token refresh scheduled in %.0f seconds",
            refresh_delay,
        )

    async def _token_refresh_after(self, delay: float) -> None:
        """
        Wait and then trigger reconnection for token refresh.

        Args:
            delay: Seconds to wait before refresh.
        """
        try:
            await asyncio.sleep(delay)

            if self._running:
                logger.info("Token refresh: triggering reconnection")
                self._reconnect_event.set()

        except asyncio.CancelledError:
            logger.debug("Token refresh task cancelled")
            raise

    def _full_topic(self, topic: str) -> str:
        """Apply topic prefix if configured."""
        if self._config.topic_prefix:
            prefix = self._config.topic_prefix.rstrip("/")
            return f"{prefix}/{topic.lstrip('/')}"
        return topic

    def _strip_topic_prefix(self, topic: str) -> str:
        """Remove topic prefix for clean callback."""
        if self._config.topic_prefix:
            prefix = self._config.topic_prefix.rstrip("/") + "/"
            if topic.startswith(prefix):
                return topic[len(prefix) :]
        return topic
