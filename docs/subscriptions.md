# Event Subscription Documentation

This document describes the **event subscription** system in the CELINE Digital Twin runtime.

The subscription system enables DT apps and external handlers to receive and react to events published via the broker.

---

## Overview

The subscription infrastructure provides:

- **SubscriptionService** for managing event subscriptions
- **MQTT subscriber** with automatic token refresh
- **Concurrent event dispatch** to handlers
- **Decorator-based** and **programmatic** registration
- **YAML configuration** for static subscriptions

---

## Quick Start

### 1. Configure subscriptions (YAML)

Create or edit `config/subscriptions.yaml`:

```yaml
subscriptions:
  - id: log-ev-charging
    topics:
      - "dt/ev-charging/#"
    handler: "celine.dt.handlers.examples:log_ev_charging_readiness"
    enabled: true
```

### 2. Create a handler

```python
# celine/dt/handlers/my_handlers.py
from celine.dt.contracts.events import DTEvent
from celine.dt.contracts.subscription import EventContext

async def log_ev_charging_readiness(event: DTEvent, context: EventContext) -> None:
    print(f"Received {event.type} on {context.topic}")
```

### 3. Or use the decorator

```python
from celine.dt.core.subscription import subscribe

@subscribe("dt/ev-charging/+/readiness")
async def handle_readiness(event: DTEvent, context: EventContext) -> None:
    print(f"EV Charging indicator: {event.payload.indicator}")
```

### 4. Or subscribe programmatically

```python
# At runtime
sub_id = await dt.subscribe(
    topics=["dt/alerts/#"],
    handler=my_alert_handler,
)

# Later, unsubscribe
await dt.unsubscribe(sub_id)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         DT Runtime                               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                  SubscriptionService                        │ │
│  │  ┌─────────────────┐    ┌─────────────────────────────────┐│ │
│  │  │SubscriptionReg. │    │     EventDispatcher             ││ │
│  │  │                 │    │  - Concurrent handler dispatch  ││ │
│  │  │ - Topic patterns│◄───│  - Error isolation              ││ │
│  │  │ - Handlers      │    │  - Metrics                      ││ │
│  │  └─────────────────┘    └─────────────────────────────────┘│ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ▲                                   │
│                              │                                   │
│  ┌───────────────────────────┴────────────────────────────────┐ │
│  │                    MqttSubscriber                           │ │
│  │  - JWT token refresh                                        │ │
│  │  - Automatic reconnection                                   │ │
│  │  - Topic management                                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   MQTT Broker    │
                    │   (Mosquitto)    │
                    └──────────────────┘
```

---

## Configuration

### Application Settings

In `.env` or environment:

```bash
# Enable/disable subscriptions
SUBSCRIPTIONS_ENABLED=true

# Maximum concurrent handler invocations
SUBSCRIPTIONS_MAX_CONCURRENT=100
```

### Subscriptions YAML

Location: `config/subscriptions.yaml`

```yaml
subscriptions:
  # Simple handler
  - id: log-all-events
    topics:
      - "dt/#"
    handler: "mymodule:log_event"
    enabled: true

  # Multiple topics
  - id: multi-topic-handler
    topics:
      - "dt/ev-charging/+/readiness"
      - "dt/pv-forecast/+/updated"
    handler: "mymodule:handle_energy_events"
    enabled: true
    metadata:
      description: "Handles energy-related events"
      owner: "energy-team"
```

---

## Topic Patterns

Subscriptions support MQTT-style topic wildcards:

| Wildcard | Description | Example |
|----------|-------------|---------|
| `+` | Matches exactly one level | `dt/ev-charging/+/readiness` matches `dt/ev-charging/rec-folgaria/readiness` |
| `#` | Matches zero or more levels | `dt/ev-charging/#` matches all under `dt/ev-charging/` |

---

## Handler Contract

Handlers must be async functions with this signature:

```python
async def my_handler(event: DTEvent, context: EventContext) -> None:
    pass
```

### EventContext

```python
@dataclass
class EventContext:
    topic: str           # Actual topic (after wildcard resolution)
    broker_name: str     # Which broker delivered this
    received_at: datetime
    message_id: str | None
    raw_payload: bytes | None
```

---

## Registration Methods

### 1. Decorator

```python
@subscribe("dt/ev-charging/#")
async def handle_ev_events(event: DTEvent, context: EventContext) -> None:
    print(f"Received: {event.type}")
```

### 2. YAML Configuration

```yaml
subscriptions:
  - id: my-handler
    topics: ["dt/ev-charging/#"]
    handler: "mymodule.handlers:my_handler"
```

### 3. Programmatic

```python
sub_id = await dt.subscribe(
    topics=["dt/alerts/#"],
    handler=alert_handler,
)
await dt.unsubscribe(sub_id)
```

---

## Token Refresh

When using JWT authentication, the subscriber automatically refreshes tokens at 80% of lifetime and reconnects seamlessly.

---

## Error Handling

Errors in handlers are logged but don't affect other handlers. Each handler runs in isolation.

---

## API Endpoints

### List Subscriptions

```
GET /subscriptions
```

Returns:
```json
{
  "subscriptions": [
    {
      "id": "my-handler",
      "topics": ["dt/ev-charging/#"],
      "enabled": true
    }
  ],
  "stats": {
    "running": true,
    "subscription_count": 3,
    "dispatch_count": 1234,
    "dispatch_errors": 2
  }
}
```
