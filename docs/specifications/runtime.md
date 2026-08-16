# Specification — runtime

Domain registration, route mounting, entity resolution and discovery.

What a domain *is*, and how to add one, is `docs/domains.md` and
`.agents/playbooks/extending-a-domain.md`. This document says only what must hold.

---

## Domain registration

### REQ-1001 — A domain MUST be registered under its `name`.

Registering a second domain with a name already held MUST be rejected.

### REQ-1002 — Two domains MUST NOT share a `route_prefix`.

Registration of the second MUST be rejected, and the error MUST name the domain already holding the prefix.

> Not the same rule as REQ-1001: the names may differ while the prefixes collide, and
> the failure then is silent shadowing rather than a duplicate.

### REQ-1003 — Every registered domain MUST expose `name`, `domain_type`, `version`, `route_prefix` and `entity_id_param`.

`route_prefix` MUST begin with `/` and MUST NOT end with one.

### REQ-1004 — A domain declared in `config/domains.yaml` MUST resolve to a module-level `DTDomain` *instance*.

A class, or an instance constructed inside a function, MUST NOT satisfy the declaration.

---

## Path resolution

The domain that serves a request is resolved from the URL at request time, not bound when
the route is mounted. These requirements are what makes that safe.

### REQ-1010 — An inbound path MUST resolve to the registered domain whose `route_prefix` is the longest prefix of that path.

### REQ-1011 — Prefix matching MUST be on segment boundaries.

A path MUST match a prefix only when it equals that prefix or continues it with `/`.

> `/about` must not resolve to the domain mounted at `/a`. A bare string-prefix test
> serves that request from the wrong domain, with a 200.

### REQ-1012 — A trailing slash MUST NOT affect resolution.

### REQ-1013 — A path matching no registered prefix MUST resolve to no domain.

---

## Route mounting

### REQ-1020 — Every registered domain MUST mount, under `{route_prefix}/{{{entity_id_param}}}`: `/info`, `/summary`, `/values`, `/simulations` and `/ontology`.

### REQ-1021 — Modules under `src/celine/dt/domains/{name}/routes/` exporting a module-level `router` MUST be discovered and mounted inside the same entity scope, at their declared `__prefix__`.

### REQ-1022 — A domain with no `routes/` package MUST mount successfully with no custom routes.

Absence MUST NOT be an error.

### REQ-1023 — Every mounted operation id MUST be prefixed with the domain name, with hyphens replaced by underscores.

> `celine-sdk` is generated from this schema. Two domains both mounting `/info` would
> otherwise collide on `get_info` and generate one method for both.

### REQ-1024 — The entity path parameter MUST appear as a path parameter in the OpenAPI document for every entity-scoped route.

> Without it the generated SDK method loses the argument that identifies the entity.

---

## Entity resolution

### REQ-1030 — The entity identifier MUST be taken from the path parameter named by `entity_id_param` and passed to the domain's `resolve_entity`.

### REQ-1031 — When `resolve_entity` returns `None`, the request MUST answer 404.

### REQ-1032 — Metadata returned by `resolve_entity` MUST be available to that request's query templates as `entity.metadata`, and to custom routes through the context.

### REQ-1033 — The default `resolve_entity` MUST accept any entity identifier.

Rejection is a domain's own responsibility.

> Stated because it is permissive and not obvious: a domain that forgets to override
> `resolve_entity` serves the entire identifier space.

---

## Authentication

### REQ-1040 — Every built-in entity-scoped route MUST require a JWT.

A request without one MUST answer 401, and MUST NOT reach entity resolution.

---

## Discovery

### REQ-1050 — `GET /health` MUST answer 200 and report the number of currently registered domains.

### REQ-1051 — `GET /domains` MUST list every registered domain with its `name`, `domain_type`, `version`, `route_prefix`, `entity_id_param` and the identifiers of its value fetchers.

### REQ-1052 — The value identifiers reported by `GET /domains` MUST be the domain-local ones, matching what the values API accepts (REQ-1103).

> These two endpoints read the domain registry through `app.state.infra`, which is the
> only application state `create_app` sets. Reading it from anywhere else reports an
> empty service with a 200 — a health check that passes while describing nothing.

---

## Domains this service ships

Not requirements — the current registry, recorded so the identifiers above have referents.
Regenerate rather than trust: `GET /domains`.

| Name | Type | Prefix | Entity parameter |
|---|---|---|---|
| `it-energy-community` | `energy-community` | `/communities/it` | `community_id` |
| `it-participant` | `participant` | `/participants` | `participant_id` |
| `it-grid` | `grid` | `/grid` | `network_id` |
