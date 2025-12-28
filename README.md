# CELINE Digital Twin (DT)

The **CELINE Digital Twin** is a modular, production‑ready runtime for building,
executing, and exposing **Digital Twin applications**.

This repository provides a **stable Digital Twin core** and a **module‑driven
extension model** that allows teams to develop, deploy, and evolve DT applications
independently while sharing a common runtime.

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

This project is a **foundation**, not a turnkey product.

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
  - adapters to external systems
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

---

## Running the DT runtime

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

Apps are registered dynamically at startup.
A reference module included in this repository is **ev_charging**, which exposes
a decision‑support Digital Twin app for EV charging readiness.

---

## Inspect app contracts

```bash
curl http://localhost:8000/apps/<app-key>/describe
```

This endpoint returns the **input and output JSON Schemas** derived from the app
models.

---

## Example: EV Charging Readiness

The `ev_charging` module provides a reference DT app that transforms weather‑driven
PV forecasts into **operational indicators for EV charging coordination**.

```bash
curl -X POST http://localhost:8000/apps/ev-charging-readiness/run   -H "Content-Type: application/json"   -d '{
    "community_id": "demo-community",
    "location": { "lat": 45.9, "lon": 11.1 },
    "window_hours": 24,
    "pv_capacity_kw": 1200,
    "ev_charging_capacity_kw": 800
  }'
```

---

## License

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
