# Domains

A **domain** is the central organising unit of the DT runtime: a self-contained vertical
bundling values, simulations, broker subscriptions and custom routes into one entity-scoped
API surface.

This document describes what a domain is and what the runtime does with it. The procedure
for adding one is the companion's playbook for adding a domain.

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
| `check_fetch(spec, payload, ctx)` | refuses a value fetch for this caller by raising `FetchRefused` (403, audited; REQ-1116); allows everything by default |

**Lifecycle** — `on_startup()`, `on_shutdown()`.

Two more hooks are optional and **not** on the base class: the built-in routes look them up
by name. `async get_summary(ctx=...)` backs `/summary`, and `async list_simulations(ctx=...)`
backs `/simulations`. No shipped domain implements either.

Infrastructure is injected by `set_infrastructure()`; shared services are reached through
`self.infra` rather than imported.

**Whose token a fetcher queries with.** A `ValueFetcherSpec` a domain returns carries
`identity`, `"caller"` by default: the caller's token is forwarded, and dataset-api narrows
the rows to that caller. A fetcher declared `identity="service"` queries with the Digital
Twin's own client-credentials token instead, and answers **503**
`service_identity_unavailable` when that token cannot be had. Only a fetcher whose rows are
the same for every caller may declare it; today that is the two reference-boundary fetchers
(REQ-1125, REQ-1129, REQ-1160; [values.md](values.md#reference-boundaries)). Fetchers are
declared in code only; there is no *config/values.yaml*.

## Routes the runtime mounts

Every domain gets these automatically at `/{route_prefix}/{entity_id_param}/`:

| Endpoint | Method | Purpose |
|---|---|---|
| `/info` | GET | entity and domain metadata |
| `/summary` | GET | the domain's own summary — **501** unless it implements `get_summary` |
| `/values` | GET | list the registered fetchers — every domain's, not only this one's: the registry is shared |
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

**Every one of these requires a JWT.** They sit behind `get_ctx_auth`, which answers 401 to a
request without a bearer token. The token is checked **before** `get_ctx` resolves the
entity, so a request without one never reaches `resolve_entity`: an unknown entity answers
401, not 404, until the caller authenticates. This holds for a `"service"` fetcher too: the Digital Twin's own token is
used only after the caller's has been checked.

`{fetcher_id}` is the **domain-local** identifier — `rec_self_consumption`, not
`it-energy-community.rec_self_consumption` — on both verbs. The `/values` listing and
`/describe` report the namespaced registry key, which is *not* the form the path takes;
the companion's knowledge has the
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
| Energy Community | `it-energy-community` | `/communities/it` | `community_id` | REC self-consumption, weather, PV, settlement, reference boundaries (`boundary_at_point`, `boundary_shape`, inherited from the base `EnergyCommunityDomain`), REC Manager Dashboard aggregates |
| Participant | `it-participant` | `/participants` | `participant_id` | meter data, flexibility, gamification, nudging |
| Grid | `it-grid` | `/grid` | `network_id` | wind and heat risk, substation topology, nowcasting |

`domain_type` is `energy-community`, `participant` and `grid` respectively.

- **Energy community** (`domains/energy_community/`). The base `EnergyCommunityDomain`
  (`base.py`) fixes type and entity parameter and returns the two reference-boundary
  fetchers from `boundary_fetchers.py`; `ITEnergyCommunityDomain` (`domain.py`) extends that
  list with its own fetchers and the `rec_*` aggregates of `manager_fetchers.py`, which feed
  the REC Manager Dashboard and select device-keyed or aggregate rows only, with the caller's
  token. Every REC read is restricted to `community_id = entity.id` (REQ-1500). The base's
  `check_fetch` gates the manager fetchers (REQ-1510): a service holding
  `digital-twin.community.manage`, `platform-admin`, or `admins`/`managers` of the community's
  organisation; every other fetcher is open to any authenticated caller. It does not override
  `resolve_entity`, so any `community_id` is accepted. Custom routes:
  `/energy-balance`, `/energy-balance/hourly`.
- **Participant** (`domains/participant/`). A participant twin is the caller's own:
  `resolve_entity` answers 403 when `participant_id` is not the verified token's `sub`, then
  asks the REC registry (`get_me`, with the caller's token) and returns `None` — 404 — when
  the caller has no membership; otherwise it puts `member_key`, `community_key` and related
  fields in `entity.metadata`. Its `check_fetch` answers 403 to a `device_id` that is not
  one of the caller's registry assets. No role is exempt
  ([participant.md](specifications/participant.md), ADR-0004). An `@on_event` handler in `events.py` runs the meter nudging when a
  `meters-flow` pipeline run completes. Custom routes: `/energy-balance`,
  `/energy-balance/hourly`, `/profile`, `/community`, `/member`, `/assets`,
  `/delivery-points`.
- **Grid** (`domains/grid/`). Read-through only. The entity is the network: the distribution
  operator's organisation alias, which every grid table carries as `dso_id`. Every read is
  restricted to `dso_id = entity.id`, because celine-grid calls with a service token that no
  dataset-api row filter narrows. `resolve_entity` admits a member of that `dso` organisation,
  or a service holding `grid.read`/`grid.admin`, and answers 403 otherwise; no realm role
  widens it ([grid.md](specifications/grid.md)). Custom route: `/substations/map`.

Registration is `config/domains.yaml`, mapping the name to an import path resolving to a
module-level `domain` instance. The YAML `name` must equal the class's `name` or startup
fails; a domain whose import fails is logged and skipped.

## Configuration

The three YAML files support `${VAR:-default}` environment expansion:

- `config/domains.yaml` — domain declarations: import path, enabled flag, overrides. The
  overrides reach the domain as `self.infra.overrides`; the runtime reads `broker`, the
  broker the domain's event handlers subscribe on unless a handler names its own
  ([Subscriptions](subscriptions.md#configuration))
- `config/clients.yaml` — data clients: class, base URL, scope, timeout
- `config/brokers.yaml` — MQTT brokers: host, port, TLS, token authentication

## Related

- `specifications/runtime.md` — what the runtime must do, as requirements with tests
- `values.md` — value fetchers in depth, including the query template reference
- `simulations.md` — the two-phase what-if model (**largely unimplemented**; see its status note)
- `subscriptions.md` — broker subscriptions and topic patterns
- `clients.md` — data client configuration and adding one
- the companion's playbook for adding a domain — the procedure for adding one
