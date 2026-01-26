# Concepts

This document explains the **core architectural concepts** of the CELINE Digital Twin runtime. Read this first to understand the mental model before diving into implementation details.

---

## The Three Artifact Types

The Digital Twin runtime is built around three artifact types, each serving a distinct purpose:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│    ┌───────────────┐    ┌───────────────┐    ┌───────────────────────┐     │
│    │     Apps      │    │  Components   │    │     Simulations       │     │
│    │               │    │               │    │                       │     │
│    │  Orchestrate  │    │    Compute    │    │      Explore          │     │
│    │  operations   │    │    (pure)     │    │      what-if          │     │
│    │               │    │               │    │                       │     │
│    │  /apps API    │    │  (internal)   │    │  /simulations API     │     │
│    └───────────────┘    └───────────────┘    └───────────────────────┘     │
│                                                                              │
│    External-facing       Internal            External-facing               │
│    Side effects OK       No side effects     Two-phase execution           │
│    One-shot execution    Stateless           Scenario + Parameters         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Apps

An **App** is a self-contained, externally-callable operation.

Key characteristics:
- Exposed via REST API (`/apps/{key}/run`)
- May have side effects (publish events, update state)
- Receives all dependencies via `RunContext`
- Contains orchestration logic, not computation

When to use: Real-time decisions, integrations, one-shot calculations.

### Components

A **Component** is a pure, reusable computation unit.

Key characteristics:
- Not directly exposed via API
- Pure: same input → same output, no side effects
- Stateless: no memory between calls
- Composable: freely combined by apps and simulations

When to use: Energy calculations, profile generation, economic models.

### Simulations

A **Simulation** enables what-if exploration with varying parameters.

Key characteristics:
- Exposed via REST API (`/simulations/{key}/...`)
- Two-phase execution: scenario (expensive) + runs (fast)
- Scenario caching for efficient parameter sweeps
- Built-in support for sensitivity analysis

When to use: Planning, optimization, scenario comparison.

---

## The Two-Phase Simulation Model

Simulations separate expensive setup from fast exploration:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   Phase 1: Build Scenario                 Phase 2: Run Simulations         │
│   (expensive, cacheable)                  (fast, parameterized)            │
│                                                                              │
│   ┌─────────────────────────┐             ┌─────────────────────────┐      │
│   │ Scenario Configuration  │             │      Parameters         │      │
│   │ - community_id          │             │ - pv_kwp: 100           │      │
│   │ - reference_period      │             │ - battery_kwh: 50       │      │
│   │ - resolution            │             │ - discount_rate: 0.05   │      │
│   └───────────┬─────────────┘             └───────────┬─────────────┘      │
│               │                                       │                     │
│               ▼                                       ▼                     │
│   ┌─────────────────────────┐             ┌─────────────────────────┐      │
│   │   build_scenario()      │             │      simulate()         │      │
│   │                         │             │                         │      │
│   │ - Fetch historical data │             │ - Load cached scenario  │      │
│   │ - Compute baseline      │             │ - Apply parameters      │      │
│   │ - Store artifacts       │             │ - Compute results       │      │
│   │ - ~seconds to minutes   │             │ - ~milliseconds         │      │
│   └───────────┬─────────────┘             └───────────┬─────────────┘      │
│               │                                       │                     │
│               ▼                                       ▼                     │
│   ┌─────────────────────────┐             ┌─────────────────────────┐      │
│   │       Scenario          │────────────▶│        Result           │      │
│   │ - scenario_id           │   reused    │ - self_consumption: 0.8 │      │
│   │ - baseline_metrics      │   many      │ - npv: €12,000          │      │
│   │ - cached_data refs      │   times     │ - payback_years: 7.2    │      │
│   └─────────────────────────┘             └─────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

This enables:
- **Parameter sweeps**: Test 100 configurations against one scenario
- **Sensitivity analysis**: See how results change with each parameter
- **Scenario comparison**: Compare different communities or time periods

---

## Registry and Registration

The **DTRegistry** is the central catalog of all artifacts:

```python
from celine.dt.core.registry import DTRegistry

registry = DTRegistry()

# Apps
registry.register_app(MyApp())

# Components  
registry.register_component(MyComponent())
# or: registry.components.register(MyComponent())

# Simulations
registry.register_simulation(MySimulation())
# or: registry.simulations.register(MySimulation())
```

The registry provides:
- Lookup by key
- Schema introspection
- Module tracking
- Ontology management

---

## RunContext: The Execution Environment

**RunContext** carries execution metadata and shared services. Apps, components, and simulations never access infrastructure directly—everything comes through context.

```python
class MyApp:
    async def run(self, config: MyConfig, context: RunContext) -> MyResult:
        # Data access
        data = await context.values.fetch("weather_forecast", {"location": "folgaria"})
        
        # State management
        state = await context.state.get("my-app")
        
        # Event publishing
        await context.publish_event(my_event)
        
        # Request metadata
        print(context.request_id)
        print(context.now)
```

Available in context:
- `values` - Value fetchers for data access
- `state` - State store for persistence
- `broker` - Event broker for publishing
- `token_provider` - Authentication tokens
- `request_id` - Unique request identifier
- `now` - Current UTC timestamp

---

## Modules: Packaging and Deployment

A **Module** is a deployable unit that groups related artifacts:

```python
# my_module/module.py
from celine.dt.core.registry import DTRegistry

class MyModule:
    name = "my-module"
    version = "1.0.0"

    def register(self, registry: DTRegistry) -> None:
        registry.register_app(MyApp())
        registry.register_component(MyComponent())
        registry.register_simulation(MySimulation())

module = MyModule()
```

Configure in `config/modules.yaml`:

```yaml
modules:
  - name: my-module
    version: ">=1.0.0"
    import: celine.dt.modules.my_module.module:module
    enabled: true
```

---

## Clients: Data Backend Abstraction

**Clients** provide data access to external systems. They are configured via YAML and support dependency injection.

```yaml
# config/clients.yaml
clients:
  dataset_api:
    class: celine.dt.core.datasets.dataset_api:DatasetSqlApiClient
    inject:
      - token_provider  # Injected from app state
    config:
      base_url: "${DATASET_API_URL}"
      timeout: 30.0
```

Clients implement a query interface:

```python
class DatasetClient(ABC):
    async def query(self, *, sql: str, limit: int, offset: int) -> list[dict]
    def stream(self, *, sql: str, page_size: int) -> AsyncIterator[list[dict]]
```

---

## Values: Declarative Data Fetching

**Values** are declarative data fetchers configured via YAML:

```yaml
# config/values.yaml
values:
  weather_forecast:
    client: dataset_api
    query: |
      SELECT * FROM weather_forecasts
      WHERE location = :location
        AND date >= :start_date
    limit: 100
    payload:
      type: object
      required: [location]
      properties:
        location: { type: string }
        start_date: { type: string, default: "2024-01-01" }
```

Access via API or code:

```bash
# API
curl "http://localhost:8000/values/weather_forecast?location=folgaria"

# Code (inside app/simulation)
data = await context.values.fetch("weather_forecast", {"location": "folgaria"})
```

---

## Brokers and Subscriptions: Event System

**Brokers** publish events to external systems (MQTT, etc.):

```yaml
# config/brokers.yaml
brokers:
  mqtt_local:
    class: celine.dt.core.broker.mqtt:MqttBroker
    config:
      host: "${MQTT_HOST:-localhost}"
      port: 1883
      topic_prefix: "celine/dt/"
```

**Subscriptions** receive events:

```yaml
# config/subscriptions.yaml
subscriptions:
  - id: log-events
    topics: ["dt/ev-charging/#"]
    handler: "my.module:handle_event"
    enabled: true
```

---

## Configuration Hierarchy

Configuration is loaded in this order:

1. **Environment variables** - Override settings
2. **Clients** (`config/clients.yaml`) - Data backends
3. **Brokers** (`config/brokers.yaml`) - Event publishers
4. **Modules** (`config/modules.yaml`) - Artifact registration
5. **Values** (`config/values.yaml` + module values) - Data fetchers
6. **Subscriptions** (`config/subscriptions.yaml`) - Event handlers

Environment variable substitution:

| Syntax | Behavior |
|--------|----------|
| `${VAR}` | Required - fails if not set |
| `${VAR:-default}` | Optional - uses default if not set |

---

## Design Principles

### 1. Transport Agnostic
Apps and simulations work identically whether called via:
- REST API
- Unit tests
- Batch jobs
- Event handlers

### 2. Infrastructure Injected
Domain logic never imports FastAPI, SQLAlchemy, or external libraries directly. Everything comes through `RunContext`.

### 3. Explicit Over Implicit
- All dependencies are visible in function signatures
- Configuration is declarative (YAML)
- Schemas are exposed automatically

### 4. Composition Over Inheritance
- Components compose freely
- Apps orchestrate components
- Simulations use components and apps

---

## Next Steps

- [Developer Guide](developer-guide.md) - Build your first app, component, or simulation
- [Simulations](simulations.md) - Deep dive into the simulation engine
- [Values API](values.md) - Configure data fetchers
