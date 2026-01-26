# CELINE Digital Twin (DT)

The **CELINE Digital Twin** is a modular, production-ready runtime for building, executing, and exposing **Digital Twin applications** for energy communities and renewable energy systems.

This repository provides a **stable Digital Twin core** and a **module-driven extension model** that allows teams to develop, deploy, and evolve DT capabilities independently while sharing a common runtime.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Concepts](docs/concepts.md) | Core architecture and mental model |
| [Developer Guide](docs/developer-guide.md) | Building apps, components, and simulations |
| [Apps](docs/apps.md) | DTApp contract, execution model, mappers |
| [Simulations](docs/simulations.md) | What-if exploration and scenario analysis |
| [Values API](docs/values.md) | Declarative data fetching |
| [Clients](docs/clients.md) | Data backend configuration |
| [Brokers](docs/brokers.md) | Event publishing (MQTT) |
| [Subscriptions](docs/subscriptions.md) | Event consumption |

---

## Architecture Overview

The Digital Twin runtime is organized around three primary artifact types:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Digital Twin Runtime                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐     ┌─────────────────┐     ┌────────────────────┐       │
│   │    Apps     │     │   Components    │     │    Simulations     │       │
│   │  /apps API  │     │   (internal)    │     │  /simulations API  │       │
│   └──────┬──────┘     └────────┬────────┘     └─────────┬──────────┘       │
│          │                     │                        │                   │
│          └─────────────────────┴────────────────────────┘                   │
│                                │                                            │
│                         ┌──────┴──────┐                                     │
│                         │  DTRegistry │                                     │
│                         └──────┬──────┘                                     │
│                                │                                            │
│   ┌────────────┐    ┌─────────┴─────────┐    ┌──────────────┐              │
│   │  Clients   │    │    RunContext     │    │   Brokers    │              │
│   │  (data)    │    │  (execution env)  │    │   (events)   │              │
│   └────────────┘    └───────────────────┘    └──────────────┘              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Apps
**External-facing operations** exposed via `/apps` API. Apps orchestrate components and may have side effects (events, state changes). They receive all dependencies via `RunContext`.

### Components
**Internal computation building blocks**. Components are pure, stateless functions that transform typed inputs into typed outputs. They wrap external libraries (pvlib, RAMP) or implement domain calculations.

### Simulations
**What-if exploration** exposed via `/simulations` API. Simulations use a two-phase execution model: build an expensive scenario once, then run fast parameter variations against it.

---

## Quick Start

### Run the DT runtime

```bash
uv run uvicorn celine.dt.main:create_app --reload
```

### Verify it's running

```bash
curl http://localhost:8000/health
```

### Discover available capabilities

```bash
# List apps
curl http://localhost:8000/apps

# List simulations
curl http://localhost:8000/simulations

# List value fetchers
curl http://localhost:8000/values
```

---

## Core Capabilities

### Modular Architecture
- Functionality delivered through **modules** configured via YAML
- Modules register apps, components, and simulations at startup
- Clean separation between runtime orchestration and domain logic

### App Execution
- Apps are self-contained, independently executable capabilities
- Transport-agnostic: same execution path for API, tests, and batch jobs
- Strong typing with Pydantic models and automatic schema exposure

### Simulation Engine
- Two-phase execution: expensive scenario build + fast parameter runs
- Scenario caching for efficient parameter sweeps
- Workspace system for managing simulation artifacts
- Built-in support for sensitivity analysis

### Pluggable Data Access
- Clients configured via YAML with dependency injection
- Values API for declarative, schema-validated data fetching
- Environment variable substitution in configurations

### Event System
- Publish computed events to MQTT brokers
- Subscribe to events with pattern matching
- Automatic token refresh for authenticated brokers

---

## Configuration

The DT runtime uses configuration files in `config/`:

| File | Purpose |
|------|---------|
| `modules.yaml` | Module registration and settings |
| `clients.yaml` | Data client definitions |
| `values.yaml` | Value fetcher definitions |
| `brokers.yaml` | Event broker configuration |
| `subscriptions.yaml` | Event subscription handlers |

Environment variables can be used with `${VAR}` or `${VAR:-default}` syntax.

---

## Example: EV Charging Readiness

The `ev_charging` module provides a reference DT app:

```bash
curl -X POST http://localhost:8000/apps/ev-charging-readiness/run \
  -H "Content-Type: application/json" \
  -d '{
    "community_id": "demo-community",
    "location": { "lat": 45.9, "lon": 11.1 },
    "window_hours": 24,
    "pv_capacity_kw": 1200,
    "ev_charging_capacity_kw": 800
  }'
```

## Example: REC Planning Simulation

The `rec_planning` module provides a what-if simulation:

```bash
# Build a scenario (expensive, cacheable)
curl -X POST http://localhost:8000/simulations/rec.rec-planning/scenarios \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "community_id": "rec-folgaria",
      "reference_start": "2024-01-01T00:00:00Z",
      "reference_end": "2024-12-31T23:59:59Z"
    },
    "ttl_hours": 24
  }'

# Run simulations with different parameters (fast)
curl -X POST http://localhost:8000/simulations/rec.rec-planning/runs \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "<scenario_id_from_above>",
    "parameters": {
      "pv_kwp": 100.0,
      "battery_kwh": 50.0
    }
  }'

# Run a parameter sweep
curl -X POST http://localhost:8000/simulations/rec.rec-planning/sweep \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "<scenario_id>",
    "parameter_sets": [
      {"pv_kwp": 50},
      {"pv_kwp": 100},
      {"pv_kwp": 150}
    ],
    "include_baseline": true
  }'
```

---

## API Reference

### Apps API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/apps` | GET | List all registered apps |
| `/apps/{key}/describe` | GET | Get app metadata and schemas |
| `/apps/{key}/run` | POST | Execute an app |

### Simulations API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/simulations` | GET | List all registered simulations |
| `/simulations/{key}/describe` | GET | Get simulation metadata and schemas |
| `/simulations/{key}/scenarios` | POST | Build a scenario |
| `/simulations/{key}/scenarios` | GET | List scenarios |
| `/simulations/{key}/scenarios/{id}` | GET | Get scenario details |
| `/simulations/{key}/runs` | POST | Run simulation with parameters |
| `/simulations/{key}/run-inline` | POST | Build scenario and run in one call |
| `/simulations/{key}/sweep` | POST | Run parameter sweep |

### Values API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/values` | GET | List all value fetchers |
| `/values/{id}/describe` | GET | Get fetcher metadata |
| `/values/{id}` | GET | Fetch data with query params |
| `/values/{id}` | POST | Fetch data with JSON body |

---

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
