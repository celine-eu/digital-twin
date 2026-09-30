# Event Subscription Documentation

This document describes the **event subscription** system in the CELINE Digital Twin runtime.

The subscription system enables DT domains and plain handler functions to receive and react to events delivered via the broker.

---

## Overview

The subscription infrastructure provides:

- **`@on_event`** (`celine.dt.core.broker.decorators`) to declare a handler
- **`scan_handlers`** (`celine.dt.core.broker.scanner`) to collect module-level handlers
- **`SubscriptionManager`** (`celine.dt.core.broker.subscriptions`) to turn them into live
  broker subscriptions
- **Error isolation** per handler

There is no YAML configuration for subscriptions. Nothing reads a *config/subscriptions.yaml*;
subscriptions come from a domain's `get_subscriptions()` and from `@on_event` handlers that
`scan_handlers` collects at startup.

---

## Quick Start

### 1. Create a handler

```python
from celine.dt.contracts.events import DTEvent
from celine.dt.contracts.subscription import EventContext

async def log_pipeline_run(event: DTEvent, context: EventContext) -> None:
    print(f"Received {event.event_type} on {context.topic}")
```

### 2. Declare it with the decorator

```python
from celine.dt.core.broker.decorators import on_event

@on_event("pipelines.run", topics=["celine/pipelines/runs/+"])
async def on_pipeline_run(event: DTEvent, context: EventContext) -> None:
    print(f"Pipeline {event.payload.flow}: {event.payload.status}")
```

It works on a domain method and on a plain module-level function. Module-level handlers are
found by `scan_handlers`, configured in `src/celine/dt/main.py`: it walks the base package of
every registered domain (e.g. `celine.dt.domains.participant`) plus any `extra_packages`.
`celine/dt/domains/participant/events.py` is the handler that exists today.

### 3. Or return specs from a domain

```python
from celine.dt.contracts.subscription import SubscriptionSpec

class MyDomain(DTDomain):
    def get_subscriptions(self) -> list[SubscriptionSpec]:
        return [
            *super().get_subscriptions(),   # keeps the @on_event methods
            SubscriptionSpec(
                topics=["dt/alerts/#"],
                handlers=[self.on_alert],
                metadata={"event_type": "alert"},
            ),
        ]
```

---

## Architecture

The subscription subsystem connects MQTT events to domain handlers:

| Component | Description |
|---|---|
| `MqttBroker` (SDK) | Connects to Mosquitto, manages JWT token refresh and reconnection |
| `BrokerService` | Named brokers; `subscribe()` / `unsubscribe()` on a named or default broker |
| `scan_handlers` | Collects `@on_event` module-level functions into `SubscriptionSpec`s |
| `SubscriptionManager` | Subscribes each spec at startup, wraps messages into `DTEvent` + `EventContext`, unsubscribes on shutdown |

`SubscriptionManager.start()` runs in the application lifespan after the brokers connect;
`stop()` runs on shutdown. Routes with the same `(broker, topics, event_type)` are grouped into
one spec with several handlers.

---

## Configuration

There are no subscription settings. What decides a subscription:

- the `@on_event` arguments: `event_type`, `topics`, `broker`, `enabled` (default `true`),
  `metadata`;
- the owning domain's `overrides.broker` in `config/domains.yaml`;
- the brokers in [`config/brokers.yaml`](brokers.md#configuration).

**Which broker.** A `broker=` named on the handler wins. Otherwise the handler's domain's
`overrides.broker` applies — for domain methods, and for plain functions found in that
domain's package. Otherwise the broker service's default. The shipped handler names none,
so `MQTT_BROKER` (default `celine_mqtt`) chooses its broker.

### Subscription specs

Built in code, not loaded from a file. `SubscriptionSpec` (`celine.dt.contracts.subscription`):

```python
@dataclass
class SubscriptionSpec:
    topics: list[str]
    handlers: list[EventHandler]
    id: str = "sub-<random>"
    enabled: bool = True
    metadata: dict[str, Any] = {}
```

Metadata keys the manager reads: `broker` (broker name), `qos` (`QoS`, int or name; default
`AT_LEAST_ONCE`), `event_type`, `entity_id`, and `source_domain`, `handler`, `version` for the
event source of a wrapped raw payload.

---

## Topic Patterns

Subscriptions support MQTT-style topic wildcards:

| Wildcard | Description | Example |
|----------|-------------|---------|
| `+` | Matches exactly one level | `dt/example/+/readiness` matches `dt/example/example-rec/readiness` |
| `#` | Matches zero or more levels | `dt/example/#` matches all under `dt/example/` |

---

## Handler Contract

Handlers must be async functions with this signature (a domain method also takes `self`):

```python
async def my_handler(event: DTEvent, context: EventContext) -> None:
    pass
```

A message whose JSON carries `@type` (or `event_type`) is parsed as a `DTEvent`; any other JSON
object is wrapped in one, with `event_type` from the spec metadata or else the topic. The
payload arrives as a Pydantic model that accepts any fields.

### EventContext

```python
@dataclass(frozen=True)
class EventContext:
    topic: str           # Actual topic (after wildcard resolution)
    broker_name: str     # Which broker delivered this
    received_at: datetime
    infra: Infrastructure  # Shared services: infra.broker, infra.values_service, ...
    entity_id: str | None = None
    message_id: str | None = None
    raw_payload: bytes | None = None

    def get_dt(self, domain_type: str) -> DTDomain: ...
```

---

## Registration Methods

### 1. Decorator

```python
@on_event("pipelines.run", topics=["celine/pipelines/runs/+"])
async def handle_runs(event: DTEvent, context: EventContext) -> None:
    print(f"Received: {event.event_type}")
```

### 2. Domain `get_subscriptions()`

Return `SubscriptionSpec`s, as in the [Quick Start](#3-or-return-specs-from-a-domain). The
default implementation returns the domain's `@on_event` methods.

### 3. Programmatic

A raw broker subscription, whose handler receives the SDK `ReceivedMessage` rather than a
`DTEvent`:

```python
res = await infra.broker.subscribe(
    topics=["dt/alerts/#"],
    handler=alert_handler,
)
await infra.broker.unsubscribe(subscription_id=res.subscription_id)
```

---

## Token Refresh

When using JWT authentication, the SDK broker refreshes the token `token_refresh_margin`
seconds (default 30) before expiry and reconnects with the new credentials.

---

## Error Handling

Errors in handlers are logged but don't affect other handlers. Each handler of a spec is
awaited in turn, each in its own `try`. A failed subscribe is logged and skipped.

---

## API Endpoints

There is no `/subscriptions` endpoint. `GET /domains` reports each domain's subscription
count (other fields omitted):

```json
[
  {
    "name": "it-participant",
    "subscriptions": 0
  }
]
```

The count is from `get_subscriptions()`; handlers found by `scan_handlers` are not counted.
