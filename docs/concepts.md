# Concepts

This document explains the **core architectural concepts** of the CELINE Digital
Twin runtime.

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

Apps:
- contain pure domain logic
- are unaware of HTTP, databases, or frameworks
- receive all context explicitly

A reference implementation is provided by the `ev_charging` module.

---

## RunContext

`RunContext` carries execution metadata and shared services.

This ensures apps remain testable and transport‑agnostic.

---

## Runner

`DTAppRunner` is the **single execution engine**.

Execution flow:
1. resolve app from registry
2. apply input mapping
3. execute app logic
4. apply output mapping