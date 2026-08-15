# Domains

A **domain** is the central organising unit of the DT runtime: a self-contained vertical
bundling values, simulations, broker subscriptions and custom routes into one entity-scoped
API surface.

This document describes what a domain is and what the runtime does with it. The procedure
for adding one is `.agents/playbooks/extending-a-domain.md`.

## What the service is

The Digital Twin is a domain-driven FastAPI service exposing entity-scoped APIs for the
CELINE verticals. It is **not** a CRUD application — it is a read-through runtime that
fetches from external sources, primarily `dataset-api`, enriches through entity context, and
optionally reacts to broker events.

Package `celine-dt`, import root `celine.dt`, port `8002`.

## Layout

The package, under `src/celine/dt/`:

| Path | What lives there |
|---|---|
| `src/celine/dt/contracts/` | protocol definitions — the framework's public API surface |
| `src/celine/dt/core/` | the domain-agnostic runtime: loader, registry, values, broker, ontology |
| `src/celine/dt/api/` | FastAPI wiring — context dependency injection, discovery routes, the domain router builder |
| `src/celine/dt/domains/` | the concrete domains |

And two trees at the **repository root**, not inside the package — they are deployment
inputs rather than code, and are mounted rather than imported:

| Path | What lives there |
|---|---|
| `config/` | YAML declarations: `domains.yaml`, `clients.yaml`, `brokers.yaml` |
| `ontologies/mapper` | CELINE ontology mapper specs, YAML to JSON-LD |

The app factory is `celine.dt.main:create_app`. Startup order is fixed and matters: OIDC
token provider → clients → domain value fetchers → brokers → subscriptions → each domain's
`on_startup()`. A domain that reaches for a client before this has finished sees nothing.

## The DTDomain contract

Every domain subclass declares:

**Identity**, all class variables — `name`, `domain_type`, `version`, `route_prefix`,
`entity_id_param`.

**Capabilities**, as overridable methods:

| Method | Returns |
|---|---|
| `get_value_specs()` | the declarative data fetchers |
| `get_simulations()` | the what-if models |
| `get_subscriptions()` | broker event handlers |
| `get_ontology_specs()` | JSON-LD concept views |
| `resolve_entity(entity_id, request)` | validates and enriches the entity from the URL |

**Lifecycle** — `on_startup()`, `on_shutdown()`.

Infrastructure is injected by `set_infrastructure()`; shared services are reached through
`self.infra` rather than imported.

## Routes the runtime mounts

Every domain gets these automatically at `/{route_prefix}/{entity_id_param}/`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/info` | GET | entity and domain metadata |
| `/summary` | GET | the domain's own summary — **501** unless it implements `get_summary` |
| `/values` | GET | list the registered fetchers |
| `/values/{fetcher_id}` | GET/POST | execute one, by query string or JSON body |
| `/values/{fetcher_id}/describe` | GET | payload schema introspection |
| `/simulations` | GET | list simulations — **501** unless the domain implements `list_simulations` |
| `/ontology` | GET | list ontology specs |
| `/ontology/{spec_id}` | GET/POST | fetch the JSON-LD document |

Two things this table used to get wrong, both verified against the mounted routes on
2026-08-15:

- `/summary` is mounted and was missing here.
- **There is no `POST /simulations/{key}`.** `GET /simulations` is the entire simulation
  surface the runtime mounts. The scenario/run/sweep API described in `simulations.md` is
  not wired to any route — see the status note at the top of that document.

**Every one of these requires a JWT.** They sit behind `get_ctx_auth`; a request without a
bearer token answers 401 and never reaches entity resolution.

`{fetcher_id}` is the **domain-local** identifier — `rec_self_consumption`, not
`it-energy-community.rec_self_consumption` — on both verbs. The `/values` listing and
`/describe` report the namespaced registry key, which is *not* the form the path takes;
`.agents/knowledge/a-fetcher-id-is-local-in-the-path-namespaced-in-the-registry.md` has the
full mapping.

Modules under `domains/{name}/routes/` are discovered and mounted alongside these, inside
the same entity scope. Globally, the service exposes `GET /health` and `GET /domains`,
neither of which is entity-scoped or authenticated.

Operation ids are namespaced per domain (`it_grid__get_info`), because `celine-sdk` is
generated from this schema and two domains would otherwise collide on the built-in routes.

The requirements behind all of this are `docs/specifications/runtime.md`.

## The domains that exist

| Domain | Name | Prefix | Entity parameter | Covers |
|---|---|---|---|---|
| Energy Community | `it-energy-community` | `/communities/it` | `community_id` | REC self-consumption, weather, PV, settlement |
| Participant | `it-participant` | `/participants` | `participant_id` | meter data, flexibility, gamification, nudging |
| Grid | `it-grid` | `/grid` | `network_id` | wind and heat risk, substation topology, nowcasting |

Registration is `config/domains.yaml`, mapping the name to an import path resolving to a
module-level `domain` instance.

## Configuration

The three YAML files support `${VAR:-default}` environment expansion:

- `config/domains.yaml` — domain declarations: import path, enabled flag, overrides
- `config/clients.yaml` — data clients: class, base URL, scope, timeout
- `config/brokers.yaml` — MQTT brokers: host, port, TLS, token authentication

## Related

- `specifications/runtime.md` — what the runtime must do, as requirements with tests
- `values.md` — value fetchers in depth, including the query template reference
- `simulations.md` — the two-phase what-if model (**largely unimplemented**; see its status note)
- `subscriptions.md` — broker subscriptions and topic patterns
- `clients.md` — data client configuration and adding one
- `.agents/playbooks/extending-a-domain.md` — the procedure for adding one
