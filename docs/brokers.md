# Event Brokers

This document describes the **event broker** system in the CELINE Digital Twin runtime.

The broker system enables DT apps to publish computed events to external systems (e.g., MQTT brokers, message queues) and subscribe to incoming events for real-time integration.

---

## Overview

The broker infrastructure provides:

- **Unified Broker protocol** for both publishing and subscribing
- **MQTT implementation** for IoT/edge scenarios
- **Token provider integration** for JWT authentication
- **Automatic reconnection** and token refresh
- **Configuration-driven** broker setup

---

## Quick Start

### 1. Configure the broker

Create or edit `config/brokers.yaml`:

```yaml
brokers:
  mqtt_local:
    class: celine.dt.core.broker.mqtt:MqttBroker
    enabled: true
    config:
      host: localhost
      port: 1883
      topic_prefix: "celine/dt/"

default_broker: mqtt_local
```

### 2. Publish events from an app

```python
from celine.dt.contracts.app import DTApp
from celine.dt.core.context import RunContext

class MyApp(DTApp[MyConfig, MyResult]):
    async def run(self, config: MyConfig, context: RunContext) -> MyResult:
        result = await self._compute(config)
        
        # Publish event if broker is available
        if context.has_broker():
            event = create_my_event(
                community_id=config.community_id,
                indicator=result.indicator,
            )
            await context.publish_event(event)
        
        return result
```

### 3. Subscribe to events

```python
from celine.dt.core.broker import MqttBroker, MqttConfig, ReceivedMessage

async def main():
    broker = MqttBroker(MqttConfig(host="localhost"))
    
    async def handle_message(msg: ReceivedMessage):
        print(f"Received on {msg.topic}: {msg.payload}")
    
    async with broker:
        # Subscribe
        result = await broker.subscribe(
            topics=["dt/my-module/#"],
            handler=handle_message,
        )
        
        # Keep running to receive messages
        await asyncio.sleep(3600)
        
        # Cleanup
        await broker.unsubscribe(result.subscription_id)
```

---

## Architecture

The broker provides a unified interface for both publishing and subscribing:

```
┌─────────────────────────────────────────────────────────────────┐
│                         DT Runtime                               │
│                                                                  │
│  ┌─────────────┐        ┌─────────────────────────────────────┐ │
│  │   DT App    │───────▶│           MqttBroker                │ │
│  └─────────────┘        │                                     │ │
│                         │  ┌─────────────┐  ┌──────────────┐  │ │
│  ┌─────────────┐        │  │  publish()  │  │ subscribe()  │  │ │
│  │  Handlers   │◀───────│  └─────────────┘  └──────────────┘  │ │
│  └─────────────┘        │                                     │ │
│                         │  • Token refresh (auto)             │ │
│                         │  • Reconnection (auto)              │ │
│                         │  • TLS support                      │ │
│                         └──────────────┬──────────────────────┘ │
└────────────────────────────────────────┼────────────────────────┘
                                         │
                                         ▼
                              ┌──────────────────┐
                              │  MQTT Broker     │
                              │  (Mosquitto)     │
                              └──────────────────┘
```

---

## Configuration

### Broker Configuration File

Location: `config/brokers.yaml`

```yaml
brokers:
  mqtt_local:
    class: celine.dt.core.broker.mqtt:MqttBroker
    enabled: true
    config:
      host: "${MQTT_HOST:-localhost}"
      port: ${MQTT_PORT:-1883}
      topic_prefix: "celine/dt/"
      keepalive: 60
      clean_session: true

  mqtt_secure:
    class: celine.dt.core.broker.mqtt:MqttBroker
    enabled: false
    config:
      host: secure-broker.example.com
      port: 8883
      use_tls: true
      ca_certs: /etc/ssl/certs/ca-certificates.crt

default_broker: mqtt_local
```

### MqttConfig Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | str | `localhost` | MQTT broker hostname |
| `port` | int | `1883` | MQTT broker port |
| `client_id` | str | auto | Unique client identifier |
| `username` | str | None | Authentication username (ignored if token_provider set) |
| `password` | str | None | Authentication password (ignored if token_provider set) |
| `use_tls` | bool | `false` | Enable TLS encryption |
| `ca_certs` | str | None | Path to CA certificate file |
| `certfile` | str | None | Path to client certificate |
| `keyfile` | str | None | Path to client private key |
| `keepalive` | int | `60` | Keepalive interval (seconds) |
| `clean_session` | bool | `true` | Start with clean session |
| `reconnect_interval` | float | `5.0` | Seconds between reconnect attempts |
| `topic_prefix` | str | `""` | Prefix for all topics |
| `token_refresh_margin` | float | `30.0` | Seconds before token expiry to refresh |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MQTT_HOST` | MQTT broker hostname | `localhost` |
| `MQTT_PORT` | MQTT broker port | `1883` |
| `MQTT_USERNAME` | Authentication username | (none) |
| `MQTT_PASSWORD` | Authentication password | (none) |

---

## Authentication

The broker supports two authentication methods:

### 1. Username/Password

Static credentials configured in `brokers.yaml`:

```yaml
brokers:
  mqtt_local:
    class: celine.dt.core.broker.mqtt:MqttBroker
    config:
      host: broker.example.com
      username: "${MQTT_USERNAME}"
      password: "${MQTT_PASSWORD}"
```

### 2. JWT via TokenProvider

For OIDC/OAuth2 authentication, pass a `TokenProvider` to the broker:

```python
from celine.sdk.auth.oidc import OidcClientCredentialsProvider
from celine.dt.core.broker import MqttBroker, MqttConfig

# Create token provider
token_provider = OidcClientCredentialsProvider(
    base_url="https://keycloak.example.com/realms/celine",
    client_id="dt-service",
    client_secret="secret",
    scope="openid",
)

# Create broker with JWT auth
broker = MqttBroker(
    config=MqttConfig(
        host="secure-broker.example.com",
        port=8883,
        use_tls=True,
    ),
    token_provider=token_provider,
)

async with broker:
    # Both publish and subscribe use JWT auth
    await broker.publish(message)
    await broker.subscribe(topics, handler)
```

When a `token_provider` is configured:
- Username is set to `"jwt"` (convention for JWT auth in Mosquitto)
- Password is set to the access token
- Tokens are automatically refreshed before expiry
- The broker reconnects seamlessly with new credentials

See [Token Providers](#token-providers) for more details.

---

## Publishing Events

### From RunContext (Recommended)

The simplest way to publish events from an app:

```python
from celine.dt.contracts.broker import QoS

class MyApp(DTApp[MyConfig, MyResult]):
    async def run(self, config: MyConfig, context: RunContext) -> MyResult:
        result = await self._compute(config)
        
        if context.has_broker():
            event = create_my_event(...)
            
            # Simple publish
            await context.publish_event(event)
            
            # With explicit QoS
            await context.broker.publish_event(
                event,
                qos=QoS.EXACTLY_ONCE,
                retain=True,
            )
        
        return result
```

### Using MqttBroker Directly

For standalone usage:

```python
from celine.dt.core.broker import MqttBroker, MqttConfig, BrokerMessage, QoS

async def standalone_publish():
    broker = MqttBroker(MqttConfig(
        host="localhost",
        topic_prefix="celine/dt/",
    ))
    
    async with broker:
        result = await broker.publish(BrokerMessage(
            topic="events/my-event",
            payload={"indicator": "OPTIMAL"},
            qos=QoS.AT_LEAST_ONCE,
        ))
        
        if result.success:
            print(f"Published: {result.message_id}")
```

### QoS Levels

| Level | Name | Description |
|-------|------|-------------|
| 0 | `AT_MOST_ONCE` | Fire and forget |
| 1 | `AT_LEAST_ONCE` | Acknowledged delivery (default) |
| 2 | `EXACTLY_ONCE` | Guaranteed single delivery |

---

## Subscribing to Events

### Using the Broker Directly

```python
from celine.dt.core.broker import MqttBroker, MqttConfig, ReceivedMessage

async def main():
    broker = MqttBroker(MqttConfig(host="localhost"))
    
    # Define handler
    async def handle_alerts(msg: ReceivedMessage):
        print(f"Alert on {msg.topic}")
        print(f"Payload: {msg.payload}")
        print(f"Received at: {msg.timestamp}")
    
    async with broker:
        # Subscribe to multiple topic patterns
        result = await broker.subscribe(
            topics=["dt/alerts/#", "dt/errors/+/critical"],
            handler=handle_alerts,
            qos=QoS.AT_LEAST_ONCE,
        )
        
        print(f"Subscribed with ID: {result.subscription_id}")
        
        # Do other work while receiving messages...
        await asyncio.sleep(3600)
        
        # Unsubscribe when done
        await broker.unsubscribe(result.subscription_id)
```

### Multiple Subscriptions

```python
async with broker:
    # Each subscription gets its own handler
    alerts_sub = await broker.subscribe(
        topics=["dt/alerts/#"],
        handler=handle_alerts,
    )
    
    metrics_sub = await broker.subscribe(
        topics=["dt/metrics/#"],
        handler=handle_metrics,
    )
    
    # Unsubscribe individually
    await broker.unsubscribe(alerts_sub.subscription_id)
    await broker.unsubscribe(metrics_sub.subscription_id)
```

### Topic Wildcards

Topic patterns follow MQTT conventions:
- `+` matches exactly one level: `dt/module/+/event` matches `dt/module/foo/event`
- `#` matches zero or more levels (must be last): `dt/module/#` matches all under `dt/module/`

### ReceivedMessage

Handlers receive a `ReceivedMessage` with:

```python
@dataclass(frozen=True)
class ReceivedMessage:
    topic: str              # Topic the message arrived on
    payload: dict[str, Any] # Parsed JSON payload
    raw_payload: bytes      # Original message bytes
    qos: QoS                # QoS level of delivery
    message_id: str | None  # Broker message ID
    timestamp: datetime     # When received
```

---

## Token Providers

Token providers enable OAuth2/OIDC authentication for brokers and other services.

### TokenProvider Protocol

```python
from abc import ABC, abstractmethod
from celine.sdk.auth.models import AccessToken

class TokenProvider(ABC):
    @abstractmethod
    async def get_token(self) -> AccessToken:
        """
        Return a valid access token.
        Implementations must refresh or re-authenticate if needed.
        """
        ...
```

### Built-in: OidcClientCredentialsProvider

For service-to-service authentication using OAuth2 client credentials flow:

```python
from celine.sdk.auth.oidc import OidcClientCredentialsProvider

provider = OidcClientCredentialsProvider(
    base_url="https://keycloak.example.com/realms/celine",
    client_id="dt-service",
    client_secret="secret",
    scope="openid profile",
    timeout=10.0,
)

# Get a token (automatically handles refresh)
token = await provider.get_token()
print(f"Access token: {token.access_token}")
print(f"Expires at: {token.expires_at}")
```

### Configuration

Configure OIDC via environment variables:

| Variable | Description |
|----------|-------------|
| `OIDC_BASE_URL` | OIDC issuer URL |
| `OIDC_CLIENT_ID` | Client ID |
| `OIDC_CLIENT_SECRET` | Client secret |

### Custom Token Provider

```python
from celine.sdk.auth.provider import TokenProvider
from celine.sdk.auth.models import AccessToken

class MyTokenProvider(TokenProvider):
    def __init__(self, api_key: str):
        self._api_key = api_key
    
    async def get_token(self) -> AccessToken:
        return AccessToken(
            access_token=self._api_key,
            expires_at=float('inf'),
        )
```

---

## Event Schemas

Events follow a common envelope pattern with type-specific payloads.

### Base Event Structure

```json
{
  "@context": "https://celine-project.eu/contexts/dt-event.jsonld",
  "@type": "dt.my-module.my-event",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "source": {
    "app_key": "my-module.my-app",
    "app_version": "1.0.0",
    "module": "my-module"
  },
  "timestamp": "2025-01-24T10:30:00Z",
  "correlation_id": "req-12345",
  "payload": { ... },
  "metadata": {}
}
```

### Core vs Module Events

The `celine.dt.contracts.events` module provides generic events:

| Type | Description |
|------|-------------|
| `dt.app.execution-started` | App execution began |
| `dt.app.execution-completed` | App execution finished |
| `dt.app.execution-failed` | App execution failed |
| `dt.alert.raised` | Alert triggered |

**Module-specific events belong in the module**, not in contracts:

```python
# ✅ Correct - import from the module
from celine.dt.modules.ev_charging.events import create_ev_charging_readiness_event

# ❌ Wrong - don't import module events from contracts
from celine.dt.contracts.events import create_ev_charging_event
```

---

## Topic Conventions

Events are published to topics following this convention:

```
{prefix}/dt/{module}/{event-type}/{entity-id}
```

Examples:
- `celine/dt/ev-charging/readiness-computed/rec-folgaria`
- `celine/dt/app/execution-completed/my-app`
- `celine/dt/alert/raised/threshold-001`

---

## Creating Custom Brokers

To implement a custom broker (e.g., Kafka, RabbitMQ):

```python
from celine.dt.contracts.broker import (
    BrokerBase,
    BrokerMessage,
    MessageHandler,
    PublishResult,
    QoS,
    ReceivedMessage,
    SubscribeResult,
)

class KafkaBroker(BrokerBase):
    def __init__(self, bootstrap_servers: str, **kwargs):
        self._servers = bootstrap_servers
        self._producer = None
        self._consumer = None
        self._subscriptions = {}
    
    async def connect(self) -> None:
        # Initialize Kafka producer and consumer
        pass
    
    async def disconnect(self) -> None:
        # Close connections
        pass
    
    async def publish(self, message: BrokerMessage) -> PublishResult:
        # Publish to Kafka topic
        pass
    
    async def subscribe(
        self,
        topics: list[str],
        handler: MessageHandler,
        qos: QoS = QoS.AT_LEAST_ONCE,
    ) -> SubscribeResult:
        # Subscribe to Kafka topics
        pass
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        # Remove subscription
        pass
    
    @property
    def is_connected(self) -> bool:
        return self._producer is not None
```

Register in `config/brokers.yaml`:

```yaml
brokers:
  kafka:
    class: mymodule.kafka:KafkaBroker
    config:
      bootstrap_servers: "kafka:9092"
```

---

## Testing

### Running Mosquitto Locally

```bash
docker run -d \
  --name mosquitto \
  -p 1883:1883 \
  eclipse-mosquitto
```

### CLI Testing

```bash
# Subscribe
mosquitto_sub -h localhost -t "celine/dt/#" -v

# Publish
mosquitto_pub -h localhost \
  -t "celine/dt/test/event/entity-1" \
  -m '{"value": 42}'
```

### Unit Testing

```python
import pytest
from unittest.mock import AsyncMock
from celine.dt.contracts.broker import ReceivedMessage, QoS

@pytest.mark.asyncio
async def test_message_handler():
    msg = ReceivedMessage(
        topic="dt/test/event",
        payload={"value": 42},
        raw_payload=b'{"value": 42}',
        qos=QoS.AT_LEAST_ONCE,
    )
    
    handler = AsyncMock()
    await handler(msg)
    
    handler.assert_called_once_with(msg)
```

---

## Next Steps

- [Apps](apps.md) - Build Digital Twin applications
- [Components](developer-guide.md#part-2-creating-a-component) - Build reusable computation units
- [Clients](clients.md) - Configure data clients
- [Values API](values.md) - Configure data fetchers