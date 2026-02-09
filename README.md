# CELINE Digital Twin – Domain-Driven Runtime (v2)

## Architecture

The DT runtime is organized around **domains** — self-contained verticals
that bundle values, simulations, broker subscriptions, and custom routes
into a cohesive, entity-scoped API surface.

```
┌─────────────────────────────────────────────────┐
│  FastAPI Application                            │
│                                                 │
│  /health  /domains                              │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │ /communities/{community_id}/...         │    │
│  │   /values/consumption_timeseries        │    │
│  │   /values/gse_incentive_rates           │    │
│  │   /simulations/rec-planning/describe    │    │
│  │   /energy-balance                       │    │
│  │   /summary                              │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │ /participants/{participant_id}/...      │    │
│  │   /values/meter_readings               │    │
│  │   /values/assets                       │    │
│  │   /profile                             │    │
│  │   /flexibility                         │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  ┌──────────────────────────┐                   │
│  │ Shared Infrastructure    │                   │
│  │  ClientsRegistry         │                   │
│  │  BrokerService           │                   │
│  │  ValuesService           │                   │
│  │  SimulationRegistry      │                   │
│  └──────────────────────────┘                   │
└─────────────────────────────────────────────────┘
```

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

Same domain type, different implementations:

```
EnergyCommunityDomain (base)
├── ITEnergyCommunityDomain  – Italian REC rules, GSE incentives
└── DEEnergyCommunityDomain  – German BEG rules, Marktstammdaten
```

### Jinja2 Query Templates

Value fetcher queries use two-phase rendering:

1. **Jinja** handles structural logic: `{{ entity.id }}`, `{% if ... %}`,
   `{{ entity.metadata.zone | sql_list }}`
2. **Bind parameters** handle safe value injection: `:start`, `:end`

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
async def resolve_entity(self, entity_id: str) -> EntityInfo | None:
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
│   └── broker.py       # Broker protocol
│
├── core/               # Runtime engine (no domain knowledge)
│   ├── config.py       # Central Settings (env-driven)
│   ├── context.py      # RunContext (per-request)
│   ├── loader.py       # YAML loading, import_attr, env substitution
│   ├── domain/         # Domain registration and wiring
│   │   ├── base.py     # DTDomain base class
│   │   ├── registry.py # DomainRegistry
│   │   ├── config.py   # YAML domain spec loader
│   │   └── loader.py   # Import + validate + register
│   ├── values/         # Data fetching subsystem
│   │   ├── template.py # Jinja2 query engine
│   │   ├── executor.py # Fetch execution
│   │   └── service.py  # Facade + registry
│   ├── broker/
│   │   └── service.py  # BrokerService + NullBrokerService
│   ├── simulation/
│   │   └── registry.py # SimulationRegistry
│   └── clients/
│       ├── registry.py # ClientsRegistry
│       └── dataset_api.py  # HTTP client for Dataset SQL API
│
├── api/                # HTTP layer
│   ├── discovery.py    # /health, /domains
│   └── domain_router.py  # Auto-generated per-domain routes
│
├── domains/            # Concrete domain implementations
│   ├── energy_community/
│   │   ├── base.py     # EnergyCommunityDomain (shared logic)
│   │   └── domain.py   # ITEnergyCommunityDomain (Italian REC)
│   └── participant/
│       └── domain.py   # ParticipantDomain + ITParticipantDomain
│
└── main.py             # Application factory (create_app)

config/
├── domains.yaml        # Domain declarations
├── clients.yaml        # Data client definitions
└── brokers.yaml        # Broker definitions

tests/
├── test_domain_registry.py
├── test_domain_routing.py
├── test_template.py
└── test_values.py
```

## Running

```bash
pip install -e ".[dev]"
uvicorn celine.dt.main:create_app --factory --reload
```

## Testing

```bash
pytest tests/ -v
```

## What Changed from v1

| v1 (artifact registry)              | v2 (domain-driven)                    |
|--------------------------------------|---------------------------------------|
| `/apps/{key}/run`                    | Gone – custom routes per domain       |
| `/simulations/{key}/scenarios`       | `/{prefix}/{id}/simulations/{key}/…`  |
| `/values/{id}`                       | `/{prefix}/{id}/values/{fetcher_id}`  |
| Flat modules.yaml                    | Domain declarations in code + YAML    |
| `:param` query substitution          | Jinja2 + bind parameters              |
| Global registry                      | Per-domain scoped capabilities        |
| DTApp as API surface                 | Custom FastAPI routers per domain     |
| Flat subscriptions.yaml              | Domain-declared reactive patterns     |
