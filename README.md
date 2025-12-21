# CELINE Digital Twin

This repository provides a **production-ready scaffold** for building Digital Twin applications for **Renewable Energy Communities (RECs)** within the CELINE ecosystem.

It is intentionally designed as a **foundation**, not a finished product: the goal is to offer a **stable core**, clear extension points, and a practical pipeline to build, test, and deploy multiple Digital Twin use cases over time.

## What this repository is

- A **FastAPI-based Digital Twin runtime**
- **Ontology-aligned** (CELINE + SAREF/SOSA/BIGG profiles)
- **Dataset-agnostic**, via pluggable adapters
- **App-oriented**, enabling multiple simulation and analysis setups
- **Production-oriented scaffold**, ready for containerization and orchestration

It is meant to support both:
- **Operational users** (e.g. REC managers, planners)
- **Researchers and developers** experimenting with models, scenarios, and KPIs

## Design philosophy

### Core + Apps separation
The platform is split into a stable **core** and pluggable **DT apps**.  
The core handles lifecycle, APIs, ontology composition, dataset access and persistence.  
DT apps encapsulate domain assumptions, simulations, KPIs and experiments.

### Ontology-first, storage-pragmatic
CELINE ontologies define the semantic contract, while relational storage is used internally for performance and simplicity. Ontology extensions are scoped to apps.

### Dataset abstraction
The Digital Twin does not assume a specific storage backend. Dataset API adapters and mappings allow integrating heterogeneous data sources while materializing only relevant slices locally.

### Scenario-driven simulations
Simulations are executed as scenarios producing persistent, comparable results. Modeling approaches are app-specific and not enforced by the core.

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
