# Specification — runtime

Domain registration, route mounting, entity resolution and discovery.

What a domain *is*, and how to add one, is `docs/domains.md` and
the companion's playbook for adding a domain. This document says only what must hold.

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

### REQ-1041 — A presented token that fails verification MUST answer 401.

An expired, wrongly signed or otherwise unverifiable token is the caller's fault, not a
server fault. The answer and the log MUST NOT repeat the verifier's message, which may
quote claims of the token.

---

## Discovery

### REQ-1050 — `GET /health` MUST answer 200 and report the number of currently registered domains.

### REQ-1051 — `GET /domains` MUST list every registered domain with its `name`, `domain_type`, `version`, `route_prefix`, `entity_id_param` and the identifiers of its value fetchers.

### REQ-1052 — The value identifiers reported by `GET /domains` MUST be the domain-local ones, matching what the values API accepts (REQ-1103).

> These two endpoints read the domain registry through `app.state.infra`, which is the
> only application state `create_app` sets. Reading it from anywhere else reports an
> empty service with a 200 — a health check that passes while describing nothing.

### REQ-1053 — Outside `dev`, `/docs`, `/redoc` and `/openapi.json` MUST answer 404 unless `CELINE_PUBLIC_DOCS` is `true`.

`1`, `yes` and `on` count as `true`; unset, empty or any other value keeps them off. In
`dev` (REQ-1061) all three are served. The environment is read as for REQ-1061.

> The API description lists every domain, entity route and value fetcher the service
> carries. A deployment that wants it public says so; none gets it by default. The rule
> is the platform's (`celine.sdk.posture.docs_urls`).

---

## Startup

### REQ-1060 — In a production environment, startup MUST fail when the service client secret is empty or equal to the client id.

Checked only when client credentials are in use, i.e. `CELINE_OIDC_BASE_URL` is non-empty.
The error MUST name the client id and say how to proceed.

> A secret equal to the client id is guessable from the client id alone, and the client
> id is public. The rule is the one celine-policies applies before writing a secret into
> a realm.

### REQ-1061 — The environment is production unless its name is exactly `dev`.

The name is read from the process environment: `CELINE_ENV`, then `ENVIRONMENT`, then the
legacy `APP_ENV` and `ENV`; the first non-empty one wins, case-insensitively. An unset or
unrecognised name — and `development`, `local`, `test`, `ci` — MUST be production. A
`.env` file does not set it.

> The strict side is the default: the cost of being strict in development is one
> exported variable; the cost the other way is a guessable secret in a live deployment.
> The rule is the platform's (`celine.sdk.posture`); until 2026-10 this service also
> relaxed `development`, `local`, `test` and `ci`.

### REQ-1062 — In a production environment, startup MUST fail when `CELINE_OIDC_BASE_URL` or `CELINE_OIDC_JWKS_URI` was not set.

The SDK defaults both to the local Keycloak, and incoming JWTs are verified against that
JWKS. A value from the environment or from code is accepted; the SDK default is not.
Every violation of REQ-1060, REQ-1062 and REQ-1063 MUST be reported in one error; in `dev`
they are logged as one warning and startup proceeds.

### REQ-1063 — In a production environment, startup MUST fail when `DATABASE_URL` carries a local-stack or trivially weak password.

The runtime opens no database itself; the check covers domains and plugins that read
`DATABASE_URL` from the same process environment. Unset is not a violation.

---

## Event subscriptions

### REQ-1070 — An `@on_event` handler that names no broker MUST subscribe on the broker its domain's `overrides.broker` names; a broker named on the handler MUST take precedence.

Holds for handlers declared as domain methods and for plain functions found in a domain's
package. With neither set, the broker service's default applies.

---

## Access audit

Records go to the `celine.audit` logger, one JSON object per line, in the platform's
shape (`celine.sdk.audit`): `event`, `service`, `sub`, `client_id`, `service_account`,
`action`, `method`, `route`, `resource`, `outcome`, `reason`, `request_id`, `trace_id`,
`ts`. The action is `twin.read`: no entity-scoped route changes a twin.

### REQ-1080 — Every request to an entity-scoped route MUST produce exactly one audit record naming the caller, the route template and the entity read.

The caller is the verified token's `sub` and client id. The resource is
`{domain}/{entity id}`, followed by any further path parameter (the value fetcher id, the
ontology spec id). A route a domain adds under `routes/` is covered like a built-in one.
A request that ends in an error is recorded with outcome `error` and the status as its
reason. `GET /health` and `GET /domains` MUST NOT be recorded.

> The query string is not recorded: it carries meter ids and time ranges, and the route
> template already says which parameters the route takes.

### REQ-1081 — A refused request MUST be recorded as `denied`, at `WARNING`, with a reason code and the caller when one was verified.

Refusals and their codes: no token (`no_token`), a token failing verification
(`invalid_token`, no caller: an unverified token names nobody), and an entity the domain's
`resolve_entity` rejects (`entity_rejected`, recorded with the caller, although the
answer is the 404 of REQ-1031). Any other 401 or 403 is recorded as `http <status>`.

### REQ-1082 — An audit record MUST NOT carry the caller's email, name or username, the token, or the query string.

An entity id shaped like an email address is replaced by its pseudonym (`h:` and 16 hex
digits).

---

## Domains this service ships

Not requirements — the current registry, recorded so the identifiers above have referents.
Regenerate rather than trust: `GET /domains`.

| Name | Type | Prefix | Entity parameter |
|---|---|---|---|
| `it-energy-community` | `energy-community` | `/communities/it` | `community_id` |
| `it-participant` | `participant` | `/participants` | `participant_id` |
| `it-grid` | `grid` | `/grid` | `network_id` |
