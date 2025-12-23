# Concepts

This document explains the **core architectural concepts** of the CELINE Digital
Twin runtime and how they interact.

---

## Digital Twin Core

The DT core is responsible for:
- application lifecycle
- module loading
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

Contract:

```python
class DTModule:
    name: str
    version: str
    def register(self, registry: DTRegistry) -> None
```

Modules are loaded at startup and validated against configuration constraints.

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

```python
class DTApp[I, O]:
    key: str
    version: str
    async def run(self, inputs: I, context: RunContext) -> O
```

Apps:
- contain pure domain logic
- are unaware of HTTP, databases, or frameworks
- receive all context explicitly

---

## Mappers

Mappers define the **public contract** of an app.

### InputMapper[T]
- converts raw payload → typed input model
- defines how external clients interact with the app

### OutputMapper[T]
- converts domain result → serializable output
- defines the external representation

Mappers are generic and type‑safe.

---

## TimeSeries

`TimeSeries[T]` is a reusable primitive representing ordered values with a fixed
timestep.

```python
TimeSeries(values=[...], timestep_hours=1.0)
```

It is used consistently across simulations and KPIs.

---

## RunContext

`RunContext` carries execution metadata and shared services.

Fields include:
- request id
- timestamp
- injected services
- optional transport metadata

This ensures apps remain testable and transport‑agnostic.

---

## Runner

`DTAppRunner` is the **single execution engine**.

Execution flow:
1. resolve app from registry
2. apply input mapper
3. execute app logic
4. apply output mapper

All execution paths (API, tests, batch) use the same runner.
