# Concepts

This document explains the **core architectural concepts** of the CELINE Digital
Twin runtime.

---

## Digital Twin Core

The DT core is responsible for:
- application lifecycle
- module loading
- client registration
- values fetcher management
- execution orchestration
- API exposure
- shared infrastructure concerns

It deliberately avoids domain‑specific logic.

---

## Modules

A **DT module** is a deployable unit of functionality.

A module:
- has a `name` and `version`
- is enabled via configuration
- registers apps into the registry
- can define module-scoped value fetchers

Modules are loaded at startup and validated against configuration constraints.

```yaml
# config/modules.yaml
modules:
  - name: ev-charging
    version: ">=1.0.0"
    import: celine.dt.modules.ev_charging.module:module
    enabled: true
    values:  # optional module-scoped fetchers
      solar_forecast:
        client: dataset_api
        query: SELECT * FROM solar WHERE location = :loc
```

---

## Registry

The **DTRegistry** is the central in‑memory catalog.

It tracks:
- loaded modules
- registered apps
- active ontology

It also provides **introspection** for discovery and documentation.

---

## Apps

A **DT app** represents a single runnable Digital Twin capability.

Apps:
- contain pure domain logic
- are unaware of HTTP, databases, or frameworks
- receive all context explicitly

A reference implementation is provided by the `ev_charging` module.

---

## RunContext

`RunContext` carries execution metadata and shared services.

This ensures apps remain testable and transport‑agnostic.

Available in context:
- `datasets` - Data client for querying external data
- `state` - State store for app state management
- `token_provider` - Authentication token provider
- `request_id` - Unique identifier for the current request
- `now` - Current UTC timestamp

---

## Runner

`DTAppRunner` is the **single execution engine**.

Execution flow:
1. resolve app from registry
2. apply input mapping
3. execute app logic
4. apply output mapping

---

## Clients

**Clients** are pluggable data backends configured via `config/clients.yaml`.

A client:
- is dynamically loaded at startup
- can receive injected services (e.g., token providers)
- implements a query interface

The `DatasetClient` protocol defines the standard interface:

```python
class DatasetClient(ABC):
    async def query(self, *, sql: str, limit: int, offset: int) -> list[dict]
    def stream(self, *, sql: str, page_size: int) -> AsyncIterator[list[dict]]
```

Clients are registered in the **ClientsRegistry** and accessed by name.

```yaml
# config/clients.yaml
clients:
  dataset_api:
    class: celine.dt.core.datasets.dataset_api:DatasetSqlApiClient
    inject:
      - token_provider
    config:
      base_url: "${DATASET_API_URL}"
```

---

## Values

**Values** are declarative data fetchers configured via YAML.

A value fetcher:
- references a client by name
- defines a query template with `:param` placeholders
- optionally validates inputs against a JSON Schema
- optionally transforms outputs via a mapper

Values are exposed via REST API:
- `GET /values` - list all fetchers
- `GET /values/{id}?params` - fetch with query parameters
- `POST /values/{id}` - fetch with JSON body
- `GET /values/{id}/describe` - get fetcher metadata

```yaml
# config/values.yaml
values:
  weather_forecast:
    client: dataset_api
    query: |
      SELECT * FROM weather_forecasts
      WHERE location = :location
    limit: 100
    payload:
      type: object
      required: [location]
      properties:
        location:
          type: string
```

### Namespacing

- Fetchers in `config/values.yaml` use their ID directly (e.g., `weather_forecast`)
- Fetchers in module configs are namespaced (e.g., `ev_charging.solar_forecast`)

---

## Configuration Hierarchy

The DT runtime loads configuration in this order:

1. **Clients** (`config/clients.yaml`)
   - Injectable services (token_provider) must be available
   - Environment variables are substituted

2. **Modules** (`config/modules.yaml`)
   - Modules are imported and validated
   - Apps are registered
   - Module-scoped values are extracted

3. **Values** (`config/values.yaml` + module values)
   - Fetchers are parsed
   - Client references are resolved
   - Output mappers are loaded

---

## Environment Variable Substitution

Configuration files support environment variable substitution:

| Syntax | Behavior |
|--------|----------|
| `${VAR}` | Required - fails if not set |
| `${VAR:-default}` | Optional - uses default if not set |

Example:

```yaml
clients:
  my_api:
    class: my.module:Client
    config:
      base_url: "${API_URL}"
      timeout: "${TIMEOUT:-30}"
```

---

## Dependency Injection

Clients can receive injected services via the `inject` list:

```yaml
clients:
  authenticated_api:
    class: my.module:AuthClient
    inject:
      - token_provider  # injected from app state
    config:
      base_url: "${API_URL}"
```

Currently available injectable services:
- `token_provider` - OIDC token provider for authenticated requests