# Concepts

This document explains the **core architectural concepts** of the CELINE Digital Twin runtime. Read this first to understand the mental model before diving into implementation details.

> **Status, verified against the code on 2026-09-30.** Parts of this document describe an
> artifact/module generation of the runtime that the **domain**-based runtime replaced, and
> they were not updated with it. Verified against `src/celine/dt/main.py`:
>
> - **No `/apps` route is mounted.** The application mounts the discovery router and one
>   router per domain, and nothing else. There is no `DTApp` contract; `DTComponent` still
>   exists under `src/celine/dt/contracts/`, but no API exposes it.
> - **There is no module registry.** No `DTRegistry`, no `register_app`, and no loader reads
>   a *config/modules.yaml*.
> - **Values and subscriptions are not YAML-configured.** See *Configuration Hierarchy*
>   below for what is actually loaded.
>
> The current organising unit is the **domain** — see [domains.md](domains.md). What should happen to the
> superseded sections is an open question for the maintainers rather than a mechanical fix,
> so they are marked rather than deleted.

---

## The Three Artifact Types

The Digital Twin runtime is built around three artifact types, each serving a distinct purpose:

| Artifact | API | Side Effects | Description |
|---|---|---|---|
| **Apps** | `/apps/{key}/run` | Allowed | Orchestrate operations, one-shot execution |
| **Components** | Internal only | None | Pure computation, stateless, composable |
| **Simulations** | `/simulations/{key}/...` | None | Two-phase what-if exploration |

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

| Phase | Function | Duration | Description |
|---|---|---|---|
| Phase 1 — Build Scenario | `build_scenario()` | seconds to minutes | Fetch historical data, compute baseline, store cached artifacts |
| Phase 2 — Run Simulations | `simulate()` | milliseconds | Load cached scenario, apply parameters, compute results |

The scenario is built once and reused many times across parameter variations. Example scenario config: `community_id`, `reference_period`, `resolution`. Example simulation parameters: `pv_kwp: 100`, `battery_kwh: 50`, `discount_rate: 0.05`. Example results: `self_consumption: 0.8`, `npv: €12,000`, `payback_years: 7.2`.

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

> **Superseded.** There is no `DTRegistry` in the current runtime. Domains are discovered
> from `config/domains.yaml` by import path, and each one is asked for its own value specs,
> simulations, subscriptions and ontology specs. `domains.md` is the current account.

---

## RunContext: The Execution Environment

**RunContext** (`celine.dt.core.context`) carries execution metadata and shared services. Domain code never accesses infrastructure directly—everything comes through context.

```python
async def handle(context: RunContext) -> None:
    # Data access: ids are namespaced "{domain.name}.{id}"; the entity is injected
    data = await context.fetch_value(
        "it-energy-community.rec_self_consumption", {"start": "...", "end": "..."}
    )

    # Event publishing
    await context.publish_event("dt/example/topic", {"ok": True})

    # Request metadata
    print(context.request_id)
    print(context.now)
```

Available in context:
- `entity` - Resolved `EntityInfo` from the URL path (or `None`)
- `values_service` - Value fetchers for data access (`fetch_value()` is the shortcut)
- `broker_service` - Event broker for publishing (`publish_event()` is the shortcut)
- `services` - Shared service bag (clients registry, etc.)
- `workspace` - Set by the simulation runner
- `request_id` - Unique request identifier
- `now` - Current UTC timestamp

There is no state store in the context.

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

> **Superseded.** The module registry above does not exist in the current runtime: there is
> no `DTRegistry`, and no loader reads a *config/modules.yaml*. Packaging a vertical is done
> by writing a `DTDomain` and declaring it in `config/domains.yaml` — see `domains.md`.

---

## Clients: Data Backend Abstraction

**Clients** provide data access to external systems. They are configured via YAML and support dependency injection.

```yaml
# config/clients.yaml
clients:
  dataset_api:
    class: celine.dt.core.clients.dataset_api:DatasetSqlApiClient
    scope: dataset.query   # OIDC scope of the client's own token
    config:
      base_url: "${DATASET_API_BASE_URL:-http://host.docker.internal:8001}"
      timeout: 30.0
```

A constructor that accepts `token_provider` gets one injected automatically; there is no
`inject:` key.

Clients implement a query interface (`DatasetSqlApiClient`):

```python
async def query(self, *, sql: str, limit: int = 1000, offset: int = 0, ctx: Ctx | None = None) -> list[dict]
def stream(self, *, sql: str, page_size: int = 1000, ctx: Ctx | None = None) -> AsyncIterator[list[dict]]
```

With a `ctx` the caller's token is forwarded; with none the client authenticates as the
Digital Twin itself, and raises `ServiceIdentityUnavailable`
(`celine.dt.core.clients.errors`) rather than send the query unauthenticated when it has
no token to use. A fetcher picks which with `identity="caller"` (default) or
`identity="service"` — see [domains.md](domains.md#the-dtdomain-contract).

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

> **Superseded.** Values are not declared in YAML. A domain returns `ValueFetcherSpec`
> objects from `get_value_specs()`, and the runtime namespaces each id as
> `{domain.name}.{id}` and mounts it under that domain's prefix — so the path is
> `/{route_prefix}/{entity_id}/values/{fetcher_id}`, not a global `/values/...`. The query
> template rules are in [values.md](values.md) and
> [specifications/query-templates.md](specifications/query-templates.md).

---

## Brokers and Subscriptions: Event System

**Brokers** publish events to external systems (MQTT, etc.):

```yaml
# config/brokers.yaml
brokers:
  celine_mqtt:
    enabled: true
    auth_with_token: true   # use the DT's OIDC token instead of username/password
    config:
      host: "${MQTT_HOST:-localhost}"
      port: "${MQTT_PORT:-1883}"
      topic_prefix: "celine/dt/"

default_broker: celine_mqtt
```

Every broker is a `celine.sdk.broker.MqttBroker`; there is no `class` key.

**Subscriptions** receive events:

```yaml
# config/subscriptions.yaml
subscriptions:
  - id: log-events
    topics: ["dt/ev-charging/#"]
    handler: "my.module:handle_event"
    enabled: true
```

> **Superseded.** There is no *config/subscriptions.yaml*. Subscriptions come from a
> domain's `get_subscriptions()` and `@on_event` handlers — see
> [subscriptions.md](subscriptions.md).

---

## Configuration Hierarchy

**The runtime loads exactly three YAML families**, and each is a *list of glob patterns*
overridable from the environment, not a fixed filename:

| Setting | Default pattern | Declares |
|---|---|---|
| `domains_config_paths` | `config/domains.yaml` | domains: name, import path, enabled, overrides |
| `clients_config_paths` | `config/clients.yaml` | data backends |
| `brokers_config_paths` | `config/brokers.yaml` | event publishers |

Three properties follow, and each one bites:

- **Opportunistic.** A pattern matching nothing logs at debug level and returns empty.
  Startup continues. A mistyped pattern is therefore indistinguishable from a feature
  nobody configured.
- **Merged.** Every file matching any pattern is loaded and sorted for determinism, then
  combined. For domains the merge key is the domain `name`, so a later file **replaces** an
  earlier declaration of the same name rather than adding a second one.
- **Environment-substituted** on load: `${VAR}` is required, `${VAR:-default}` is not.

Domains are declared **in code** as `DTDomain` subclasses; the YAML selects and tunes them.

Values and subscriptions are **not** YAML-configured at all. Value fetchers come from a
domain's `get_value_specs()`; subscriptions come from `get_subscriptions()` and from
`@on_event` handlers collected by `scan_handlers`. Files named *config/values.yaml*,
*config/subscriptions.yaml* and *config/modules.yaml* appear elsewhere in this document set
and **do not exist and are read by nothing**.

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
