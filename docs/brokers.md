# Event Brokers

This document describes the **event broker** system in the CELINE Digital Twin runtime.

The broker system enables DT domains to publish computed events to external systems (e.g., MQTT brokers, message queues) and subscribe to incoming events for real-time integration.

---

## Overview

The broker protocol and its MQTT implementation live in `celine-sdk` (`celine.sdk.broker`);
`celine.dt.contracts.broker` re-exports them unchanged. The runtime adds:

- **`BrokerService`** (`celine.dt.core.broker.service`) — a named registry of broker
  instances with a default, `connect_all()` / `disconnect_all()`, and `publish_event()`,
  `subscribe()`, `unsubscribe()` helpers. `NullBrokerService` is the no-op variant.
- **`load_and_register_brokers`** (`celine.dt.core.broker.loader`) — builds one SDK
  `MqttBroker` per entry in `config/brokers.yaml`
- **Token provider integration** for JWT authentication, with refresh before expiry
- **Automatic reconnection**, handled by the SDK `MqttBroker`

The broker service is `infra.broker` on the shared `Infrastructure`. Brokers are loaded and
connected in the application lifespan, before subscriptions start and before each domain's
`on_startup()`, and disconnected on shutdown.

---

## Quick Start

### 1. Configure the broker

Edit `config/brokers.yaml` (the path comes from `Settings.brokers_config_paths`):

```yaml
brokers:
  celine_mqtt:
    enabled: true
    auth_with_token: true
    config:
      host: "${MQTT_HOST:-host.docker.internal}"
      port: "${MQTT_PORT:-1883}"

default_broker: celine_mqtt
```

### 2. Publish from a domain route

Route handlers receive a `Ctx` (`celine.dt.api.context`), whose `publish()` goes through the
broker service:

```python
async def handler(ctx: ITCommunityCtx = Depends(get_it_community_ctx)):
    result = await compute(ctx)
    await ctx.publish(f"celine/dt/example/{ctx.entity.id}", result)  # Pydantic model or dict
    return result
```

`publish()` returns `None` when no broker service is present. From an event handler, publish
through `ctx.infra.broker.publish_event(topic=..., payload=...)`.

### 3. Subscribe to events

Declare a handler with `@on_event`; see [Subscriptions](subscriptions.md). Raw SDK
subscriptions are also available:

```python
from celine.sdk.broker import MqttBroker, MqttConfig, ReceivedMessage

async def main():
    broker = MqttBroker(MqttConfig(host="localhost"))

    async def handle_message(msg: ReceivedMessage):
        print(f"Received on {msg.topic}: {msg.payload}")

    await broker.connect()
    result = await broker.subscribe(
        topics=["celine/dt/example/#"],
        handler=handle_message,
    )

    # Keep running to receive messages
    await asyncio.sleep(3600)

    await broker.unsubscribe(result.subscription_id)
    await broker.disconnect()
```

---

## Architecture

The SDK `Broker` protocol is used for both publishing and subscribing. `BrokerService` holds
the named instances; `SubscriptionManager` subscribes `@on_event` handlers through it. The
SDK `MqttBroker` manages the connection to Mosquitto with token refresh and reconnection.

| Feature | Description |
|---|---|
| `publish()` | Emit a message to a topic |
| `subscribe()` | Register a callback handler for a list of topic patterns |
| Token refresh | Access token refreshed `token_refresh_margin` seconds before expiry |
| Reconnection | Automatic reconnect on connection loss |
| TLS support | Configurable TLS for production deployments |

---

## Configuration

### Broker Configuration File

Location: `config/brokers.yaml`. The shipped file:

```yaml
brokers:
  celine_mqtt:
    enabled: true
    auth_with_token: true
    config:
      host: "${MQTT_HOST:-host.docker.internal}"
      port: "${MQTT_PORT:-1883}"
      use_tls: "${MQTT_USE_TLS:-false}"
      keepalive: 60
      clean_session: true
      token_refresh_margin: 30.0
      # Static credentials (ignored when token_provider is active):
      # username: "${MQTT_USERNAME:-}"
      # password: "${MQTT_PASSWORD:-}"

default_broker: celine_mqtt
```

Per entry:

| Key | Description |
|-----|-------------|
| `enabled` | `false` skips the entry (default `true`) |
| `auth_with_token` | `true` injects the runtime's OIDC token provider (default `false`) |
| `config` | Keyword arguments for `MqttConfig`; numeric and boolean strings are coerced |

`${VAR}` and `${VAR:-default}` are substituted from the environment; a `${VAR}` with no value
and no default is an error. Every entry becomes a `celine.sdk.broker.MqttBroker`: there is no
`class` key. Without `default_broker`, the first registered broker is the default.

### MqttConfig Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | str | `localhost` | MQTT broker hostname |
| `port` | int | `1883` | MQTT broker port |
| `client_id` | str | `celine-<random>` | Unique client identifier |
| `username` | str | None | Authentication username (ignored if token_provider set) |
| `password` | str | None | Authentication password (ignored if token_provider set) |
| `use_tls` | bool | `false` | Enable TLS encryption |
| `ca_certs` | str | None | Path to CA certificate file |
| `certfile` | str | None | Path to client certificate |
| `keyfile` | str | None | Path to client private key |
| `keepalive` | int | `60` | Keepalive interval (seconds) |
| `clean_session` | bool | `true` | Start with clean session |
| `reconnect_interval` | float | `5.0` | Seconds between reconnect attempts |
| `max_reconnect_attempts` | int | `0` | Reconnect attempts, `0` = unlimited |
| `topic_prefix` | str | `""` | Prefix for all topics |
| `token_refresh_margin` | float | `30.0` | Seconds before token expiry to refresh |
| `connect_timeout` | float | `10.0` | Seconds to wait for the connection |

### Environment Variables

Read by the shipped `config/brokers.yaml`:

| Variable | Description | Default |
|----------|-------------|---------|
| `MQTT_HOST` | MQTT broker hostname | `host.docker.internal` |
| `MQTT_PORT` | MQTT broker port | `1883` |
| `MQTT_USE_TLS` | Enable TLS | `false` |
| `MQTT_USERNAME` | Authentication username (commented out) | (none) |
| `MQTT_PASSWORD` | Authentication password (commented out) | (none) |

---

## Authentication

The broker supports two authentication methods:

### 1. Username/Password

Static credentials in the entry's `config`, used when `auth_with_token` is off or no token
provider is configured:

```yaml
brokers:
  celine_mqtt:
    config:
      host: broker.example.com
      username: "${MQTT_USERNAME}"
      password: "${MQTT_PASSWORD}"
```

### 2. JWT via TokenProvider

At startup the runtime builds an `OidcClientCredentialsProvider` from `settings.oidc`
(`create_token_provider` in `celine.dt.core.auth`) and passes it to every broker entry with
`auth_with_token: true`. Standalone, pass one to the SDK broker directly:

```python
from celine.sdk.auth import OidcClientCredentialsProvider
from celine.sdk.broker import MqttBroker, MqttConfig

token_provider = OidcClientCredentialsProvider(
    base_url="https://keycloak.example.com/realms/celine",
    client_id="dt-service",
    client_secret="secret",
    scope="openid",
)

broker = MqttBroker(
    config=MqttConfig(
        host="secure-broker.example.com",
        port=8883,
        use_tls=True,
    ),
    token_provider=token_provider,
)
```

When a `token_provider` is configured:
- Username is set to the access token
- Password is set to `"jwt"`
- Tokens are refreshed `token_refresh_margin` seconds before expiry
- The broker reconnects with the new credentials

See [Token Providers](#token-providers) for more details.

---

## Publishing Events

### Through BrokerService

`publish_event()` accepts a Pydantic model (serialized with `model_dump(mode="json")`), a dict,
or a primitive (wrapped as `{"value": str(payload)}`):

```python
from celine.sdk.broker import QoS

result = await infra.broker.publish_event(
    topic="celine/dt/example/entity-1",
    payload=event,
    broker_name=None,          # default broker
    qos=QoS.EXACTLY_ONCE,
    retain=True,
)
if not result.success:
    print(result.error)
```

A publish failure is logged and returned as `PublishResult(success=False, error=...)`, not
raised. `Ctx.publish(topic, payload, **kw)` and `RunContext.publish_event(topic, payload,
broker_name=...)` delegate to it.

### Using MqttBroker Directly

For standalone usage:

```python
from celine.sdk.broker import MqttBroker, MqttConfig, BrokerMessage, QoS

async def standalone_publish():
    broker = MqttBroker(MqttConfig(
        host="localhost",
        topic_prefix="celine/dt/",
    ))

    await broker.connect()
    result = await broker.publish(BrokerMessage(
        topic="events/my-event",
        payload={"indicator": "OPTIMAL"},
        qos=QoS.AT_LEAST_ONCE,
    ))

    if result.success:
        print(f"Published: {result.message_id}")
    await broker.disconnect()
```

### QoS Levels

| Level | Name | Description |
|-------|------|-------------|
| 0 | `AT_MOST_ONCE` | Fire and forget |
| 1 | `AT_LEAST_ONCE` | Acknowledged delivery (default) |
| 2 | `EXACTLY_ONCE` | Guaranteed single delivery |

---

## Subscribing to Events

In the runtime, subscriptions are declared with `@on_event` and materialized by
`SubscriptionManager`; see [Subscriptions](subscriptions.md). `BrokerService.subscribe(topics=...,
handler=..., broker_name=..., qos=...)` and `unsubscribe(subscription_id=..., broker_name=...)`
are the underlying calls.

### Using the Broker Directly

```python
from celine.sdk.broker import MqttBroker, MqttConfig, QoS, ReceivedMessage

async def main():
    broker = MqttBroker(MqttConfig(host="localhost"))

    async def handle_alerts(msg: ReceivedMessage):
        print(f"Alert on {msg.topic}")
        print(f"Payload: {msg.payload}")
        print(f"Received at: {msg.timestamp}")

    await broker.connect()
    # Subscribe to multiple topic patterns
    result = await broker.subscribe(
        topics=["dt/alerts/#", "dt/errors/+/critical"],
        handler=handle_alerts,
        qos=QoS.AT_LEAST_ONCE,
    )

    print(f"Subscribed with ID: {result.subscription_id}")

    # Do other work while receiving messages...
    await asyncio.sleep(3600)

    await broker.unsubscribe(result.subscription_id)
    await broker.disconnect()
```

Each `subscribe()` call gets its own handler and `subscription_id`, and is unsubscribed
individually.

### Topic Wildcards

Topic patterns follow MQTT conventions:
- `+` matches exactly one level: `dt/module/+/event` matches `dt/module/foo/event`
- `#` matches zero or more levels (must be last): `dt/module/#` matches all under `dt/module/`

When `topic_prefix` is set, it is prepended to every published topic and subscribed pattern.

### ReceivedMessage

Handlers receive a `ReceivedMessage` with:

```python
@dataclass(frozen=True)
class ReceivedMessage:
    topic: str                      # Topic the message arrived on
    payload: dict[str, Any]         # Parsed JSON payload
    raw_payload: bytes              # Original message bytes
    qos: QoS = QoS.AT_LEAST_ONCE    # QoS level of delivery
    message_id: str | None = None   # Broker message ID
    timestamp: datetime | None = None  # When received
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
        """Return a valid access token (refreshing/re-authenticating as needed)."""
        ...
```

### Built-in: OidcClientCredentialsProvider

For service-to-service authentication using OAuth2 client credentials flow:

```python
from celine.sdk.auth import OidcClientCredentialsProvider

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

The runtime's provider comes from `Settings.oidc` (`celine.sdk.settings.models.OidcSettings`,
env prefix `CELINE_OIDC_`):

| Variable | Description |
|----------|-------------|
| `CELINE_OIDC_BASE_URL` | OIDC issuer URL; empty disables the token provider |
| `CELINE_OIDC_CLIENT_SECRET` | Client secret (default `svc-digital-twin`, refused in production — see below) |
| `CELINE_OIDC_SCOPE` | OAuth2 scope |
| `CELINE_OIDC_VERIFY_SSL` | Verify TLS certificates |

The client id is fixed to `svc-digital-twin` in `celine.dt.core.config`.

In production, `create_app` refuses to start while `CELINE_OIDC_BASE_URL` is set and the
secret is empty or equal to the client id. The environment name is read from `APP_ENV`,
`CELINE_ENV` or `ENV`; only `dev`, `development`, `local`, `test` and `ci` are
non-production, and unset means production.

### Custom Token Provider

```python
from celine.sdk.auth import AccessToken, TokenProvider

class MyTokenProvider(TokenProvider):
    def __init__(self, api_key: str):
        super().__init__()
        self._api_key = api_key

    async def get_token(self) -> AccessToken:
        return AccessToken(
            access_token=self._api_key,
            expires_at=float('inf'),
        )
```

---

## Event Schemas

`celine.dt.contracts.events.DTEvent[T]` is the common envelope, with a typed Pydantic payload.
It serializes as:

```json
{
  "@type": "example.event-computed",
  "@context": "https://celine-project.eu/contexts/dt-event.jsonld",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "source": {
    "domain": "it-energy-community",
    "entity_id": "example-rec",
    "handler": null,
    "version": "unknown"
  },
  "timestamp": "2025-01-24T10:30:00+00:00",
  "correlation_id": "req-12345",
  "payload": { ... },
  "metadata": {}
}
```

`correlation_id` is omitted when unset. `EventSource` and `EventSeverity` are in the same
module. `celine.dt.contracts.events` defines no concrete event types: payload models belong
with the domain that produces or consumes them (for instance the SDK's `PipelineRunEvent`,
consumed by `celine.dt.domains.participant.events`).

---

## Topic Conventions

No topic scheme is enforced; the publisher chooses the topic, and `topic_prefix` is prepended
when set. Topics in use:

- `celine/pipelines/runs/+` — pipeline run events, subscribed by the participant domain

---

## Creating Custom Brokers

To implement a custom broker (e.g., Kafka, RabbitMQ), subclass the SDK `BrokerBase`:

```python
from celine.dt.contracts.broker import (
    BrokerBase,
    BrokerMessage,
    MessageHandler,
    PublishResult,
    QoS,
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

`config/brokers.yaml` only builds `MqttBroker`s, so register a custom broker in code, before
the lifespan runs `connect_all()`:

```python
infra.broker.register("kafka", KafkaBroker(bootstrap_servers="kafka:9092"))
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

- [Subscriptions](subscriptions.md) - React to broker events
- [Domains](domains.md) - Build Digital Twin domains
- [Clients](clients.md) - Configure data clients
- [Values API](values.md) - Configure data fetchers