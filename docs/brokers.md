# Event Broker Documentation

This document describes the **event broker** system in the CELINE Digital Twin runtime.

The broker system enables DT apps to publish computed events to external systems
(e.g., MQTT brokers, message queues) for real-time integration with downstream consumers.

---

## Overview

The broker infrastructure provides:

- **Abstract Broker protocol** for message publishing
- **MQTT implementation** for IoT/edge scenarios
- **Event schemas** for type-safe event publishing
- **Broker service** for high-level operations
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

### 2. Set environment variables (optional)

```bash
export MQTT_HOST=mosquitto.local
export MQTT_PORT=1883
```

### 3. Publish events from an app

```python
from celine.dt.contracts.events import create_ev_charging_event

# In your app's run method:
event = create_ev_charging_event(
    community_id="rec-folgaria",
    window_start=start,
    window_end=end,
    indicator="OPTIMAL",
    confidence=0.85,
    # ... other fields
)

result = await context.publish_event(event)
if result.success:
    print(f"Published: {result.message_id}")
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         DT Runtime                            │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────┐ │
│  │   DT App    │──▶│  RunContext │──▶│   BrokerService     │ │
│  └─────────────┘   └─────────────┘   └──────────┬──────────┘ │
│                                                  │            │
│                                      ┌───────────┴──────────┐ │
│                                      │   BrokerRegistry     │ │
│                                      │  ┌────────────────┐  │ │
│                                      │  │  MqttBroker    │  │ │
│                                      │  └────────┬───────┘  │ │
│                                      └───────────┼──────────┘ │
└──────────────────────────────────────────────────┼────────────┘
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
  # Broker name (used for reference)
  mqtt_local:
    # Import path to broker class
    class: celine.dt.core.broker.mqtt:MqttBroker
    # Enable/disable this broker
    enabled: true
    # Configuration passed to constructor
    config:
      host: "${MQTT_HOST:-localhost}"
      port: ${MQTT_PORT:-1883}
      username: "${MQTT_USERNAME:-}"
      password: "${MQTT_PASSWORD:-}"
      use_tls: false
      topic_prefix: "celine/dt/"
      keepalive: 60
      clean_session: true

# Default broker when none specified
default_broker: mqtt_local
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MQTT_HOST` | MQTT broker hostname | `localhost` |
| `MQTT_PORT` | MQTT broker port | `1883` |
| `MQTT_USERNAME` | Authentication username | (none) |
| `MQTT_PASSWORD` | Authentication password | (none) |

### Application Settings

In `celine/dt/core/config.py`:

```python
# Enable/disable broker publishing
broker_enabled: bool = True

# Publish app execution events
broker_publish_app_events: bool = True

# Publish computed result events
broker_publish_computed_events: bool = True
```

---

## Event Schemas

Events follow a common envelope pattern with type-specific payloads.

### Base Event Structure

```json
{
  "@context": "https://celine-project.eu/contexts/dt-event.jsonld",
  "@type": "dt.ev-charging.readiness-computed",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "source": {
    "app_key": "ev-charging-readiness",
    "app_version": "1.1.0",
    "module": "ev-charging",
    "instance_id": "dt-instance-1"
  },
  "timestamp": "2025-01-24T10:30:00Z",
  "correlation_id": "req-12345",
  "payload": {
    // Type-specific payload
  },
  "metadata": {}
}
```

### EV Charging Readiness Event

Type: `dt.ev-charging.readiness-computed`

```json
{
  "@type": "dt.ev-charging.readiness-computed",
  "payload": {
    "community_id": "rec-folgaria",
    "window_start": "2025-01-24T00:00:00Z",
    "window_end": "2025-01-25T00:00:00Z",
    "window_hours": 24,
    "expected_pv_kwh": 5100.0,
    "ev_charging_capacity_kwh": 19200.0,
    "pv_ev_ratio": 0.266,
    "indicator": "SUBOPTIMAL",
    "confidence": 0.78,
    "drivers": [
      "expected PV energy is low relative to EV charging capacity",
      "high cloud cover expected during the window"
    ],
    "recommendations": [
      "Recommend delayed charging or reduced charging power.",
      "Prioritize critical charging sessions; consider off-peak tariffs."
    ],
    "mean_clouds_pct": 65.0,
    "clouds_std_pct": 12.5,
    "solar_energy_kwh_per_m2": 3.2
  }
}
```

### App Execution Events

#### Execution Started
Type: `dt.app.execution-started`

```json
{
  "@type": "dt.app.execution-started",
  "payload": {
    "app_key": "ev-charging-readiness",
    "request_id": "req-12345",
    "config_hash": "abc123"
  }
}
```

#### Execution Completed
Type: `dt.app.execution-completed`

```json
{
  "@type": "dt.app.execution-completed",
  "payload": {
    "app_key": "ev-charging-readiness",
    "request_id": "req-12345",
    "duration_ms": 1234,
    "result_type": "EVChargingReadiness",
    "result_summary": {
      "indicator": "OPTIMAL",
      "confidence": 0.92
    }
  }
}
```

#### Execution Failed
Type: `dt.app.execution-failed`

```json
{
  "@type": "dt.app.execution-failed",
  "payload": {
    "app_key": "ev-charging-readiness",
    "request_id": "req-12345",
    "error_type": "ValueError",
    "error_message": "Invalid location coordinates",
    "severity": "error"
  }
}
```

---

## Topic Conventions

Events are published to topics following this convention:

```
{prefix}/dt/{module}/{event-type}/{entity-id}
```

Examples:
- `celine/dt/ev-charging/readiness-computed/rec-folgaria`
- `celine/dt/app/execution-completed/ev-charging-readiness`
- `celine/dt/alert/raised/threshold-breach-001`

---

## MQTT Implementation

### Features

- Automatic reconnection handling
- TLS/SSL support
- QoS level support (0, 1, 2)
- Message retention
- JSON payload serialization
- Topic prefixing

### TLS Configuration

```yaml
brokers:
  mqtt_secure:
    class: celine.dt.core.broker.mqtt:MqttBroker
    config:
      host: secure-broker.example.com
      port: 8883
      use_tls: true
      ca_certs: /etc/ssl/certs/ca-certificates.crt
      certfile: /path/to/client.crt
      keyfile: /path/to/client.key
```

### QoS Levels

| Level | Name | Description |
|-------|------|-------------|
| 0 | AT_MOST_ONCE | Fire and forget |
| 1 | AT_LEAST_ONCE | Acknowledged delivery (default) |
| 2 | EXACTLY_ONCE | Guaranteed single delivery |

---

## Usage in Apps

### Basic Publishing

```python
from celine.dt.contracts.events import create_ev_charging_event
from celine.dt.contracts.broker import QoS

class MyApp:
    async def run(self, config, context):
        # Compute result
        result = await self._compute(config)
        
        # Create event
        event = create_ev_charging_event(
            community_id=config.community_id,
            indicator=result.indicator,
            # ... other fields
        )
        
        # Publish
        await context.publish_event(event)
        
        return result
```

### Checking Broker Availability

```python
if context.has_broker():
    await context.publish_event(event)
else:
    logger.info("No broker configured, skipping event")
```

### Using Named Brokers

```python
# Publish to a specific broker
await context.broker.publish_event(
    event,
    broker_name="mqtt_backup",
)
```

---

## Testing

### Running Mosquitto Locally

Using Docker:

```bash
docker run -d \
  --name mosquitto \
  -p 1883:1883 \
  -p 9001:9001 \
  eclipse-mosquitto
```

### Subscribing to Events

```bash
mosquitto_sub -h localhost -t "celine/dt/#" -v
```

### Publishing Test Events

```bash
mosquitto_pub -h localhost \
  -t "celine/dt/ev-charging/readiness-computed/test" \
  -m '{"@type": "dt.ev-charging.readiness-computed", "payload": {"indicator": "OPTIMAL"}}'
```

---

## Creating Custom Brokers

To implement a custom broker (e.g., Kafka, RabbitMQ):

```python
from celine.dt.contracts.broker import BrokerBase, BrokerMessage, PublishResult

class KafkaBroker(BrokerBase):
    def __init__(self, bootstrap_servers: str, **kwargs):
        self._servers = bootstrap_servers
        self._producer = None
    
    async def connect(self) -> None:
        # Initialize Kafka producer
        pass
    
    async def disconnect(self) -> None:
        # Close producer
        pass
    
    async def publish(self, message: BrokerMessage) -> PublishResult:
        # Publish to Kafka topic
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