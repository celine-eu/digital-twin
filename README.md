# CELINE Digital Twin

## Architecture

The DT runtime is organized around **domains** — self-contained verticals
that bundle values, simulations, broker subscriptions, and custom routes
into a cohesive, entity-scoped API surface.

The FastAPI application exposes global routes (`/health`, `/domains`) and per-domain route groups. Each domain generates its own URL prefix at startup. Current domain route groups:

| Domain | Route Prefix | Example value fetchers |
|---|---|---|
| Energy Community | `/communities/it/{community_id}` | `rec_self_consumption`, `rec_self_consumption_daily`, `rec_settlement_1h`, `weather_current`, `pv_potential_forecast`, `boundary_at_point`, `boundary_shape` |
| Participant | `/participants/{participant_id}` | `meters_data`, `meter_forecast`, `meter_anomalies`, `rec_participant_points`, `rec_points_leaderboard` |
| Grid | `/grid/{network_id}` | `risks`, `risks_now`, `tile_index`, `shapes`, `trendline`, `filters` |

Fetchers are reached at `/{route_prefix}/{entity_id}/values/{fetcher_id}`, GET or POST,
with a bearer token. **Don't trust the table** — it is a snapshot, and the authoritative
list is `GET /domains`, which reports every domain's fetchers from the live registry.

Every domain also mounts `/info`, `/summary`, `/values`, `/simulations` and `/ontology`
under its entity scope, plus whatever its `routes/` package exports. The full surface is
[docs/domains.md](docs/domains.md); what it must do is
[docs/specifications/](docs/specifications/index.md).

All domains share common infrastructure:

| Component | Description |
|---|---|
| `ClientsRegistry` | Manages data client instances (Dataset API, external services) |
| `BrokerService` | MQTT connection and publish/subscribe |
| `ValuesService` | Value fetcher registry and execution |
| `SimulationRegistry` | Simulation scenario registry |

## Key Concepts

### DTDomain

The central abstraction. A domain defines:

- **Identity**: `name`, `domain_type`, `route_prefix`, `entity_id_param`
- **Values**: Declarative data fetchers with Jinja2-templated queries
- **Simulations**: Scenario/parameter what-if models
- **Subscriptions**: Reactive broker event handlers
- **Custom routes**: FastAPI routers for domain-specific endpoints
- **Entity resolution**: Optional validation/enrichment callback

### Multi-Instance Domains

Same domain type, different implementations. A domain-type base class holds what every
locale shares; a locale subclass adds its own rules and data sources:

| Base | Implementation | Rules |
|---|---|---|
| `EnergyCommunityDomain` | `ITEnergyCommunityDomain` | Italian REC rules, GSE incentives |
| `ParticipantDomain` | `ITParticipantDomain` | Italian participant, REC registry integration |
| `GridDomain` | `ITGridDomain` | Italian grid resilience (wind/heat risks, CIM topology, nowcasting) |

Only Italian implementations exist today. `EnergyCommunityDomain` itself declares the
reference-boundary fetchers (`boundary_at_point`, `boundary_shape`) so every locale
inherits them; a locale extends `super().get_value_specs()` rather than replacing it
([ADR-0003](docs/decisions/ADR-0003-boundary-fetchers-live-in-the-energy-community-domain.md)).

### Jinja2 Query Templates

Value fetcher queries use two-phase rendering:

1. **Jinja** handles structural logic: `{{ entity.id }}`, `{% if ... %}`,
   `{{ entity.metadata.zone | sql_list }}`

2. **Bind parameters** handle safe value injection: `:start`, `:end`. They are
   substituted only outside quoted literals, so a `:name` inside a string (one a
   template wrote, or one `sql_list`/`sql_quote` rendered from a caller's value) stays
   text. Templates must not use `E'...'` literals.

```sql
SELECT timestamp, kwh
FROM consumption
WHERE community_id = '{{ entity.id }}'
  AND timestamp >= :start
  AND timestamp < :end
  {% if entity.metadata.boundary %}
  AND participant_id IN {{ entity.metadata.boundary | sql_list }}
  {% endif %}
```

### Entity Resolution

Optional per-domain callback:

```python
async def resolve_entity(self, entity_id: str, request: Request) -> EntityInfo | None:
    # Return None → 404
    # Return EntityInfo with metadata → available in templates + context
    record = await self.lookup(entity_id)
    if not record:
        return None
    return EntityInfo(
        id=entity_id,
        domain_name=self.name,
        metadata={"gse_zone": record.zone},
    )
```

### Fetcher Identity

A `ValueFetcherSpec` sets whose token its client sends: `identity="caller"` (the default)
forwards the caller's token, so dataset-api narrows rows to that caller;
`identity="service"` uses the Digital Twin's own OIDC client-credentials token, for open
reference data only (the boundary fetchers). When no service token can be had the client
raises `ServiceIdentityUnavailable` (`core/clients/errors.py`) and the values routes answer
503 `service_identity_unavailable`. See [docs/domains.md](docs/domains.md#the-dtdomain-contract).

### Configuration

Domains are declared in code and registered via YAML with env expansion:

```yaml
# config/domains.yaml
domains:
  - name: it-energy-community
    import: celine.dt.domains.energy_community.domain:domain
    enabled: true
    overrides:
      broker: "${MQTT_BROKER:-celine_mqtt}"
```

## Package Structure

```
src/celine/dt/
├── contracts/          # Protocols and data types (no dependencies)
│   ├── entity.py       # EntityInfo
│   ├── events.py       # DTEvent envelope
│   ├── component.py    # DTComponent protocol
│   ├── simulation.py   # DTSimulation protocol
│   ├── subscription.py # SubscriptionSpec
│   ├── values.py       # ValueFetcherSpec
│   ├── ontology.py     # OntologySpec
│   ├── infrastructure.py # Infrastructure handed to each domain
│   ├── routes.py       # Response schemas of the generic routes
│   └── broker.py       # Broker protocol (re-exported from celine-sdk)
│
├── core/               # Runtime engine (no domain knowledge)
│   ├── config.py       # Central Settings (env-driven)
│   ├── context.py      # RunContext (per-request)
│   ├── loader.py       # YAML loading, import_attr, env substitution
│   ├── auth.py         # Token provider, incoming JWT parsing
│   ├── router_discovery.py # Autodiscovers a domain's routes/ package
│   ├── domain/         # Domain registration and wiring
│   │   ├── base.py     # DTDomain base class
│   │   ├── registry.py # DomainRegistry
│   │   ├── config.py   # YAML domain spec loader
│   │   ├── loader.py   # Import + validate + register
│   │   └── routes/     # info, summary, values, simulations, ontology
│   ├── values/         # Data fetching subsystem
│   │   ├── template.py # Jinja2 query engine
│   │   ├── executor.py # Fetch execution
│   │   └── service.py  # Facade + registry
│   ├── broker/
│   │   ├── service.py  # BrokerService + NullBrokerService
│   │   └── subscriptions.py # SubscriptionManager
│   ├── ontology/
│   │   └── service.py  # OntologyService
│   ├── simulation/
│   │   └── registry.py # SimulationRegistry
│   └── clients/
│       ├── registry.py # ClientsRegistry
│       ├── loader.py   # Reads clients.yaml
│       ├── dataset_api.py  # HTTP client for Dataset SQL API
│       └── errors.py   # ServiceIdentityUnavailable
│
├── api/                # HTTP layer
│   ├── discovery.py    # /health, /domains
│   ├── dependencies.py # JWT user, RunContext dependencies
│   ├── context.py      # Per-request domain context (Depends)
│   └── domain_router.py  # Auto-generated per-domain routes
│
├── domains/            # Concrete domain implementations
│   ├── energy_community/
│   │   ├── base.py     # EnergyCommunityDomain (shared logic)
│   │   ├── domain.py   # ITEnergyCommunityDomain (Italian REC)
│   │   ├── boundary_fetchers.py # boundary_at_point, boundary_shape
│   │   ├── manager_fetchers.py  # Aggregates for the REC Manager Dashboard
│   │   └── routes/     # balance.py
│   ├── participant/
│   │   ├── domain.py   # ParticipantDomain + ITParticipantDomain
│   │   ├── nudging/    # Nudging events from meter anomalies
│   │   └── routes/     # assets.py, balance.py, profile.py
│   └── grid/
│       ├── domain.py   # GridDomain + ITGridDomain
│       ├── queries.py  # Grid-specific query templates
│       └── routes/     # wind.py, heat.py, substations.py
│
└── main.py             # Application factory (create_app)

config/
├── domains.yaml        # Domain declarations
├── clients.yaml        # Data client definitions
└── brokers.yaml        # Broker definitions

tests/
├── sample_domain/      # Minimal domain used by the routing tests
├── test_boundary_fetchers.py
├── test_domain_registry.py
├── test_domain_routing.py
├── test_domain_specs.py
├── test_manager_fetchers.py
├── test_template.py
├── test_traceability.py
└── test_values.py
```

## Documentation

**Current**, and describing the domain-driven runtime as it is:

| Document | Description |
|---|---|
| [Domains](docs/domains.md) | What a domain is, what the runtime mounts for it, and the domains that exist |
| [Specifications](docs/specifications/index.md) | What the service must do — requirements, each with a verifying test |
| [Values](docs/values.md) | Value fetchers, their HTTP surface, and Jinja2 query templates |
| [Subscriptions](docs/subscriptions.md) | Reactive broker event handlers, subscription specs |
| [Brokers](docs/brokers.md) | MQTT broker configuration, authentication, publishing/subscribing |
| [Clients](docs/clients.md) | Client configuration, dependency injection, environment substitution |
| [Decisions](docs/decisions/index.md) | Why a technical choice was made here |

**Partly superseded**, kept for the design they explain — each carries a banner saying
which parts no longer describe the code:

| Document | Read it for |
|---|---|
| [Concepts](docs/concepts.md) | the configuration hierarchy; the Apps/Components/Modules sections are superseded |
| [Developer Guide](docs/developer-guide.md) | start at "Building here, today"; Parts 1–6 teach a runtime that no longer exists |
| [Apps](docs/apps.md) | the execution model; no `/apps` route is mounted |
| [Simulations](docs/simulations.md) | the two-phase design; only `GET /simulations` is wired, and it answers 501 |

Working on this repository as an agent starts at `AGENTS.md`.

## Running

```bash
uv sync           # or: task setup
task run
# Listens on http://localhost:8002
```

`task run` and `task debug` export `CELINE_ENV=dev` (`docker compose up` still defaults the
legacy `APP_ENV` to `dev`). Anywhere else an unset environment is hardened — only
`CELINE_ENV=dev` relaxes — and a hardened start refuses the placeholder service secret,
the SDK's local Keycloak issuer/JWKS defaults and a development `DATABASE_URL` password, all
listed in one error ([Brokers](docs/brokers.md#configuration-1),
[REQ-1060–1063](docs/specifications/runtime.md#startup)). `CELINE_ENV=staging task run` is
the prod-like mode of the same entry point. `.env.example` lists the variables the service
reads.

Outside dev, `/docs`, `/redoc` and `/openapi.json` are off unless `CELINE_PUBLIC_DOCS=true`
([REQ-1053](docs/specifications/runtime.md#discovery)). Every request to an entity route
writes one record — caller, route, entity, outcome — to the `celine.audit` logger
([Access audit](docs/specifications/runtime.md#access-audit)).

## Testing

```bash
uv run pytest -q   # or: task test
```

No external service is required — the dataset client and the JWT check are the only things
faked.

## What Changed from v1

| v1 (artifact registry)              | v2 (domain-driven)                    |
|--------------------------------------|---------------------------------------|
| `/apps/{key}/run`                    | Gone – custom routes per domain       |
| `/simulations/{key}/scenarios`       | Gone – only `GET /{prefix}/{id}/simulations` is mounted |
| `/values/{id}`                       | `/{prefix}/{id}/values/{fetcher_id}`  |
| Flat modules.yaml                    | Domain declarations in code + YAML    |
| `:param` query substitution          | Jinja2 + bind parameters              |
| Global registry                      | Per-domain scoped capabilities        |
| DTApp as API surface                 | Custom FastAPI routers per domain     |
| Flat subscriptions.yaml              | Domain-declared reactive patterns     |
