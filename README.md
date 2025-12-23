# CELINE Digital Twin (DT)

The **CELINE Digital Twin** is a modular, production‑ready runtime for building,
executing, and exposing **Digital Twin applications** for energy systems such as
Renewable Energy Communities (RECs), microgrids, and scenario‑based simulations.

This repository provides a **stable Digital Twin core** and a **module‑driven
extension model** that allows teams to develop, deploy, and evolve multiple DT
applications independently while sharing a common runtime.

---

## Documentation

- [Concepts](docs/concepts.md)
- [Create a new module](docs/create-module.md)


---

## What this repository provides

- A **FastAPI‑based DT runtime**
- A **module system** for loading DT capabilities at startup
- An **app‑oriented execution model**
- Strong **typing and schema introspection**
- A clean separation between:
  - runtime orchestration
  - domain logic
  - data access
- A reference **battery sizing simulation**

This project is a **foundation**, not a turnkey product. It is designed to scale
in complexity without accumulating architectural debt.

---

## Core capabilities

### Modular DT runtime
- DT functionality is delivered through **modules**
- Modules are configured via YAML and loaded dynamically
- Each module may register one or more **DT apps**

### App‑oriented execution
- Each DT app is a **self‑contained capability**
- Apps can be:
  - simulations
  - analyses
  - adapters to external datasets
- Apps are independently executable and discoverable

### Strong contracts & schemas
- Inputs and outputs are defined using **Pydantic models**
- Schemas are exposed dynamically via API
- Clients can discover contracts at runtime

### Transport‑agnostic execution
- Apps do not depend on FastAPI or HTTP
- The same execution path is used for:
  - REST API
  - unit tests
  - batch jobs
  - future workers

### Ontology‑aware, storage‑pragmatic
- Ontologies define semantic intent
- Relational storage is used internally where needed
- Ontology loading is centralized and configurable

---

## Running the DT runtime

Start the runtime in development mode:

```bash
uv run uvicorn celine.dt.main:create_app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

---

## Discover available apps

```bash
curl http://localhost:8000/apps
```

Example response:

```json
[
  { "key": "battery-sizing", "version": "2.0.0" }
]
```

---

## Inspect app contracts

```bash
curl http://localhost:8000/apps/battery-sizing/describe
```

This endpoint returns the **input and output JSON Schemas** derived from the app
mappers and models.

---

## Run the battery sizing simulation

```bash
curl -X POST http://localhost:8000/apps/battery-sizing/run   -H "Content-Type: application/json"   -d '{
    "demand": { "values": [5, 5, 5, 5], "timestep_hours": 1 },
    "pv": { "values": [0, 10, 10, 0], "timestep_hours": 1 },
    "roundtrip_efficiency": 0.9,
    "max_capacity_kwh": 20
  }'
```

Example response:

```json
{
  "@type": "BatterySizingResult",
  "capacityKWh": 20.0,
  "gridImportKWh": 0.0,
  "selfConsumptionRatio": 1.0
}
```

---

## License

Copyright >=2025 Spindox Labs

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
