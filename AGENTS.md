# Digital Twin — AGENTS.md

## Overview

The Digital Twin (DT) is a domain-driven FastAPI service that exposes entity-scoped APIs for different CELINE verticals (energy community, participant, grid). It is **not** a traditional CRUD application — it is a read-through runtime that fetches data from external sources (primarily `dataset-api`), enriches it via entity context, and optionally reacts to MQTT broker events.

Package: `celine-dt`, import root: `celine.dt`, port: `8002`.

## Architecture

```
contracts/          Protocol definitions — the public API surface of the framework
core/               Domain-agnostic runtime engine (loader, registry, values, broker, ontology)
api/                FastAPI wiring (context DI, discovery routes, domain router builder)
domains/            Concrete domain implementations (energy_community, participant, grid)
config/             YAML declarations (domains.yaml, clients.yaml, brokers.yaml)
ontologies/mapper/  CELINE ontology mapper specs (YAML → JSON-LD)
```

The app factory is `celine.dt.main:create_app`. Lifespan initialises services in order: OIDC token provider → clients → domain value fetchers → brokers → subscriptions → domain `on_startup()`.

## Core abstractions

### DTDomain (`core/domain/base.py`)

Central organising unit. Every domain subclass declares:

- **Identity**: `name`, `domain_type`, `version`, `route_prefix`, `entity_id_param` (all `ClassVar`)
- **Capabilities** (override these methods):
  - `get_value_specs() -> list[ValueFetcherSpec]` — declarative data fetchers
  - `get_simulations() -> list[DTSimulation]` — what-if models
  - `get_subscriptions() -> list[SubscriptionSpec]` — broker event handlers
  - `get_ontology_specs() -> list[OntologySpec]` — JSON-LD concept views
  - `resolve_entity(entity_id, request) -> EntityInfo | None` — validate/enrich entity from URL
- **Lifecycle**: `on_startup()`, `on_shutdown()`

Infrastructure is injected via `set_infrastructure()`. Access shared services through `self.infra`.

Pattern: base class per domain type (e.g. `GridDomain`), then locale subclass (e.g. `ITGridDomain`).

### ValueFetcherSpec (`contracts/values.py`)

Declarative query definition: `id`, `client`, `query` (Jinja2 template), `payload_schema` (JSON Schema), `output_mapper`.

**Two-phase query rendering** (`core/values/template.py`):
1. **Jinja2** for structural logic: `{{ entity.id }}`, `{% if risk_vector %}`, `{{ dates | sql_list }}`
2. **Bind parameters** for safe value injection: `:date_from`, `:date_to` → quoted via `sql_quote`

Available Jinja filters: `sql_list` (list → `('a','b','c')`), `sql_quote` (value → escaped literal).

Entity context is always available as `{{ entity.id }}`, `{{ entity.metadata.* }}` in templates.

Fetcher IDs are namespaced at runtime as `{domain.name}.{id}` (e.g. `it-grid.risks`).

### DTSimulation (`contracts/simulation.py`)

Two-phase what-if protocol:
1. `build_scenario(config, workspace, context)` — expensive data fetch + baseline (cached on disk)
2. `simulate(scenario, parameters, context)` — fast parameter variation against cached scenario

Generic over 4 Pydantic types: `[ScenarioConfig, Scenario, Parameters, Result]`.

### Broker events (`contracts/subscription.py`, `core/broker/decorators.py`)

MQTT event handling via `@on_event` decorator:

```python
@on_event("pipeline.run.completed", topics=["celine/pipelines/runs/+"])
async def on_run(self, event: DTEvent, ctx: EventContext) -> None:
    ...
```

Works on domain methods and plain module functions. `EventContext` provides: `topic`, `broker_name`, `infra`, `entity_id`.

### Request context (`api/context.py`)

`Ctx` dataclass injected via `Depends(get_ctx)` or `Depends(get_ctx_auth)` (requires JWT).

Contains: `entity`, `domain`, `values_service`, `broker_service`, `user`, `token`.

Convenience methods: `ctx.fetch_value(fetcher_id, payload)`, `ctx.publish(topic, payload)`.

## Auto-mounted routes

Every domain automatically gets these endpoints at `/{route_prefix}/{entity_id_param}/`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/values` | GET | List fetchers for this domain |
| `/values/{fetcher_id}` | GET/POST | Execute fetcher (query params or JSON body) |
| `/values/{fetcher_id}/describe` | GET | Payload schema introspection |
| `/simulations` | GET | List simulations |
| `/simulations/{key}` | POST | Run simulation |
| `/ontology` | GET | List ontology specs |
| `/ontology/{spec_id}` | GET/POST | Fetch JSON-LD document |
| `/info` | GET | Entity + domain metadata |

Custom routes in `domains/{name}/routes/*.py` are auto-discovered. Each module exports `router: APIRouter`, optional `__prefix__`, `__tags__`.

Global: `GET /health`, `GET /domains`.

## Current domains

| Domain | Name | Prefix | Entity param | Purpose |
|---|---|---|---|---|
| Energy Community | `it-energy-community` | `/communities/it` | `community_id` | REC self-consumption, weather, PV, settlement |
| Participant | `it-participant` | `/participants` | `participant_id` | Meter data, flexibility, gamification, nudging |
| Grid | `it-grid` | `/grid` | `network_id` | Wind/heat risk, substation topology, nowcasting |

Registration: `config/domains.yaml` maps `name` → `import` path → module-level `domain` instance.

## Configuration

**YAML configs** (support `${VAR:-default}` env expansion):
- `config/domains.yaml` — domain declarations (import path, enabled flag, overrides)
- `config/clients.yaml` — data clients (class, base URL, scope, timeout)
- `config/brokers.yaml` — MQTT brokers (host, port, TLS, token auth)

**Key env vars:**
- `LOG_LEVEL` (default: `INFO`)
- `DATASET_API_BASE_URL` (default: `http://host.docker.internal:8001`)
- `REC_REGISTRY_URL` (default: `http://host.docker.internal:8004`)
- `MQTT_HOST` / `MQTT_PORT` / `MQTT_USE_TLS`
- `CELINE_OIDC_CLIENT_SECRET`, `OIDC_TOKEN_BASE_URL`

## Dependencies

FastAPI + uvicorn, Pydantic + pydantic-settings, SQLModel + Alembic (PostgreSQL), httpx, aiomqtt, pandas/numpy, Jinja2, jsonschema, celine-sdk (auth + broker + OpenAPI clients), celine-ontologies (mapper). Python ≥3.12.

## Task commands

```
task run              # uvicorn :8002 with reload
task debug            # with debugpy on :48002
task test             # pytest
task alembic:migrate  # upgrade head
task alembic:sync-model  # autogenerate revision
task alembic:reset    # downgrade base
task release          # semantic-release + push
```

## Implementation directives

### Adding a new domain

1. Create `src/celine/dt/domains/{name}/domain.py`
2. Subclass `DTDomain`, set `name`, `domain_type`, `version`, `route_prefix`, `entity_id_param`
3. Override `get_value_specs()` to define data fetchers with SQL templates against `dataset-api`
4. Optionally override `resolve_entity()` to validate entity IDs or enrich `EntityInfo.metadata`
5. Create `routes/` subpackage for custom endpoints (export `router: APIRouter`)
6. Register in `config/domains.yaml` with import path to module-level `domain = MyDomain()` instance
7. The runtime auto-mounts `/values`, `/simulations`, `/ontology`, `/info`, plus custom routes

### Adding a value fetcher

Define a `ValueFetcherSpec` in the domain's `get_value_specs()`:
- `id`: short local name (auto-namespaced as `{domain}.{id}`)
- `client`: must match a key in `config/clients.yaml`
- `query`: Jinja2 SQL template — use `{{ }}` for structural parts, `:param` for bind values
- `payload_schema`: JSON Schema for input validation (clients see it via `/describe`)
- For list filtering use `{{ values | sql_list }}`, for safe scalar injection use `:param_name`

### Adding custom routes

Create a module in `domains/{name}/routes/`, export:
- `router = APIRouter()` (required)
- `__prefix__ = "/my-prefix"` (optional, default `""`)
- `__tags__ = ["My Tag"]` (optional)

Use `Depends(get_ctx)` or `Depends(get_ctx_auth)` for the request context. Call `ctx.fetch_value("fetcher_id", payload)` to use registered value fetchers.

### Adding event handlers

Use `@on_event` decorator on domain methods:

```python
from celine.dt.core.broker.decorators import on_event

class MyDomain(DTDomain):
    @on_event("my.event.type", topics=["celine/my/topic/+"])
    async def handle_event(self, event: DTEvent, ctx: EventContext) -> None:
        ...
```

For module-level handlers (no domain): decorated plain functions are discovered via `scan_handlers()` configured in `main.py`.

### Query template rules

- Structural SQL (conditional clauses, joins, table names) → Jinja2 `{% if %}` / `{{ }}`
- User-supplied scalar values → bind parameters `:param_name`
- Lists for `IN` clauses → `{{ param | sql_list }}` (renders as `('v1', 'v2')`)
- Entity context → `{{ entity.id }}`, `{{ entity.metadata.zone }}`
- PostgreSQL casts (e.g. `::date`, `::text`) are safe — the bind-param regex uses negative lookbehind to skip `::`

### Testing

Tests live in `tests/`. Use `pytest-asyncio` for async tests. Mock the dataset client for value fetcher tests. Domain registry and routing tests don't require external services.

### Conventions

- `src/celine/dt/` layout for cross-package compatibility
- Pydantic `BaseSettings` for configuration, defaults target local dev
- `host.docker.internal` for cross-service references
- Conventional commits (`feat:`, `fix:`, `perf:`, `up:`) for `semantic-release`
- `ruff` for linting (line-length 100), `mypy` for type checking
