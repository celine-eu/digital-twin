# Specification — values

Value fetcher registration, execution, validation and pagination.

How to write a fetcher is `docs/values.md` and
the companion's playbook for adding a domain. This document says only what must hold.

---

## Registration

### REQ-1100 — Every fetcher a domain declares MUST be registered under `{domain.name}.{spec.id}`.

Registering the same namespaced identifier twice MUST be rejected.

### REQ-1101 — A fetcher naming a client that `config/clients.yaml` does not declare MUST fail startup, and the error MUST name the fetcher, the missing client and the clients that are available.

> Failing loudly is the requirement. A fetcher wired to a client that does not exist can
> never answer, and deferring the discovery to the first request turns a startup fault into
> an intermittent one.

---

## Addressing

### REQ-1103 — `GET` and `POST` on `/values/{fetcher_id}` MUST both accept the
**domain-local** identifier — `consumption`, not `it-energy-community.consumption` — and
MUST resolve it against the registry under the current entity's domain.

> One resource, one identifier. `celine-sdk` sends the local id, so every consumer does.
> A verb that took the namespaced form instead would answer only to callers that knew
> which verb they were using.

### REQ-1104 — `GET /values` MUST list the fetchers registered for the service, each with its identifier and its spec.

### REQ-1105 — `GET /values/{fetcher_id}/describe` MUST return the fetcher's spec, including its `payload_schema`, so a caller can discover what the fetcher accepts.

### REQ-1106 — An unknown fetcher identifier MUST answer 404 on every values endpoint — fetch by either verb, and describe.

> Not 500. An identifier in the path that names nothing is a missing resource; answering
> 500 makes a client error indistinguishable from a service fault, and the client retries.

---

## Payload validation

### REQ-1110 — When a fetcher declares a `payload_schema`, the request payload MUST be validated against it, and a payload that fails validation MUST answer 400 carrying the validation detail.

### REQ-1111 — Schema defaults MUST be applied to absent properties before validation.

### REQ-1112 — A supplied value MUST NOT be overwritten by that property's default.

### REQ-1113 — Applying defaults MUST NOT mutate the caller's payload object.

> The payload is often a request-scoped dict shared across a fan-out; mutating it leaks one
> fetcher's defaults into the next fetcher's input.

### REQ-1114 — A fetcher with no `payload_schema` MUST accept any payload.

### REQ-1115 — When a fetcher declares a `payload_schema`, a NaN or infinite number anywhere in the payload MUST answer 400, and MUST NOT reach the data client; the answer and the log MUST name the property and MUST NOT carry the value.

> JSON Schema's `number` admits NaN, and NaN passes every `minimum` and `maximum`, so the
> schema alone let a `lat` of NaN through to `boundary_at_point`'s statement as `nan`, which
> the database cannot read: a 500 for a client error.

---

## Execution

### REQ-1120 — The rendered query MUST be executed through the client named by the fetcher's spec.

### REQ-1121 — The request context MUST be passed to the client with the query, unless the fetcher declares the service identity (REQ-1125).

> This is what carries the caller's identity to `dataset-api`. It was threaded through the
> executor in a refactor that the test doubles did not follow.
>
> It is also why no requirement here says which meters a participant's query may reach, or
> what a participant who holds no meter gets back. The Digital Twin never builds that list:
> `dataset-api`'s `rec_registry` row filter resolves the caller's meters from the registry and
> narrows the rows. A caller with no meter is that filter's case — no rows, never an empty
> `IN ()` — and it is specified in `dataset-api` (`docs/dataspace-row-filters.md`, RF-11),
> not here.

### REQ-1125 — A fetcher that declares `identity="service"` MUST reach its client with no request context, so that the client authenticates with the Digital Twin's own service token and MUST NOT forward the caller's token; the route MUST still require an authenticated caller.

> For open reference data only, whose rows do not depend on who asks (ADR-0003). The
> caller still needs a token the Digital Twin accepts, which is `digital-twin.values.read`;
> it needs nothing on `dataset-api`. A fetcher that omits `identity` is a `"caller"`
> fetcher, and REQ-1121 holds for it.

### REQ-1126 — When `dataset-api` answers an error, the Digital Twin's log MUST carry the status and a short code derived from the status, and MUST NOT carry the response body.

> `dataset-api`'s error body can quote the statement, and a statement carries the payload's
> literals — for `boundary_at_point`, a supply address's coordinates. The reason for a
> refusal is in `dataset-api`'s own log.

### REQ-1127 — The Digital Twin's log MUST NOT carry a rendered statement or any part of it; a fetch is logged by its fetcher id, limit and offset only.

> The statement carries the payload's literals — for `boundary_at_point`, a supply
> address's coordinates. The log line used to carry the statement's first 80 characters,
> which kept the coordinates out only because they happened to come later.

### REQ-1128 — The `Authorization` header the Digital Twin sends to `dataset-api` MUST carry exactly one `Bearer` scheme followed by the token, whether the token is the caller's or the Digital Twin's own.

> The request context holds the caller's token without its scheme, and the client used to
> add `Bearer` twice, so a forwarded token reached `dataset-api` as `Bearer Bearer <token>`.
> `dataset-api`'s JWT parsing tolerated it; another receiver need not.

### REQ-1129 — When a fetcher that declares `identity="service"` (REQ-1125) is fetched and the Digital Twin has no token provider configured, or its token provider fails to obtain a token, the fetch MUST answer 503 with the code `service_identity_unavailable`, and MUST NOT send the statement to `dataset-api`.

> With no provider there is no identity of the Digital Twin's own, and the client used to
> send the statement with no `Authorization` header at all: an unauthenticated query, and a
> 500 once `dataset-api` refused it. It is a deployment fault (no OIDC client credentials),
> so a coded 503 rather than a crash. A `"caller"` fetcher is unaffected: it forwards the
> caller's token, provider or not.
>
> Amended: a provider that is configured but cannot obtain a token (the identity provider
> is down, or refuses the client credentials) used to surface as a 500. For the caller it is
> the same fault as no provider: the Digital Twin has no identity to query with right now.
> The log line carries the code and the exception type only.

### REQ-1122 — When a fetcher declares an `output_mapper`, it MUST be applied to every returned row.

### REQ-1123 — A failing output mapper MUST propagate rather than yield partial results.

### REQ-1124 — A fetcher declaring no query MUST send an empty statement to the client rather than a null one.

---

## Pagination

### REQ-1130 — `limit` and `offset` supplied on the request MUST override the spec's declared defaults; absent, the spec's values MUST apply.

### REQ-1131 — `limit` and `offset` MUST NOT be forwarded to the query template as bind parameters.

They control pagination, not the statement.

### REQ-1132 — The result MUST report the `limit` and `offset` actually applied, and the number of rows returned.

---

## Row limits

### REQ-1140 — A fetcher's `limit` MUST cover the widest window its payload schema permits, at the granularity and row multiplicity the underlying table actually produces.

> `dataset-api` caps at `MAX_LIMIT = 10_000` and applies `LIMIT` **after** `ORDER BY`, so
> an over-limit window silently drops the newest rows and the trend simply stops before
> today — with a 200 and no error.
>
> This requirement is **not currently satisfied** by
> `it-energy-community.rec_self_consumption`. The sizing arithmetic behind it, and why
> watching the displayed numbers cannot verify a fix, is
> the companion's knowledge. Tracked as an issue; see that entry.

---

## Reference boundaries

Two fetchers answer questions about published reference boundaries — for Italy, the GSE
conventional primary-substation areas, one shape per substation code. `boundary_at_point`
names the boundary that covers a point; `boundary_shape` returns the shapes of named
boundaries. They live in the energy-community domain, and `source` is their extension point
([ADR-0003](../decisions/ADR-0003-boundary-fetchers-live-in-the-energy-community-domain.md)).
How the table is chosen from `source` is REQ-1214. The route surface, payloads and answers
are in `docs/values.md` (reference boundaries).

### REQ-1150 — `boundary_at_point` and `boundary_shape` MUST declare `source` as a required, closed enum in their `payload_schema`, whose only value is `gse_cabine_primarie`.

> Another country's boundaries are a new enum value and a new template branch, not a new
> fetcher and never a table name taken from the request.

### REQ-1151 — A `source` outside that enum MUST answer 400, and MUST NOT reach the data client.

> REQ-1110 gives the 400. The second half is the point: a refused source is refused before any
> statement is rendered.

### REQ-1152 — `boundary_at_point` MUST require `lat` and `lon` as numbers within −90..90 and −180..180 (WGS 84 degrees), and MUST answer 400 for a value outside those ranges.

### REQ-1153 — `boundary_at_point` MUST answer at most one row, and that row's `id` MUST name a boundary of the requested source whose shape covers the point.

> "Covers" includes the shape's edge. A containment test that excludes the edge answers
> nothing for a point on a line two boundaries share, which reads as "outside every
> boundary" to a caller deciding eligibility.

### REQ-1154 — A point that no boundary of the source covers MUST answer 200 with no rows.

> No match is an answer, not an error. The caller decides what "outside" means.

### REQ-1155 — A point covered by more than one boundary — on an edge they share, or where two shapes overlap — MUST answer the boundary with the lowest `id` in lexical order, the same on every call.

> The source's areas are meant to tile the territory, so this is the edge case. What matters
> is that the answer is one id and does not change between the wizard and the approval that
> re-checks it.

### REQ-1156 — `boundary_shape` MUST answer one row per requested `id` that the source knows, carrying that `id` and its shape as GeoJSON, and MUST NOT answer any `id` that was not requested.

### REQ-1157 — An `id` the source does not know MUST be absent from the `boundary_shape` answer, not an error.

> A caller validating a list of ids compares what it asked for with what came back. Failing
> the whole request would hide which id was unknown.

### REQ-1158 — An empty `ids` MUST answer 200 with no rows, and MUST NOT send a statement containing an empty list to the data client.

> `IN ()` is a syntax error in PostgreSQL; `dataset-api` answers it 400 and the fetcher 500s.
> See REQ-1234 and REQ-1235.

### REQ-1159 — `boundary_shape` MUST declare a `maxItems` for `ids`, and its `limit` MUST be at least that `maxItems`.

> REQ-1140 applied to a list rather than a window: one row per id, so the widest request the
> schema permits is `maxItems` rows. A lower limit silently drops the last shapes with a 200.

### REQ-1160 — `boundary_at_point` and `boundary_shape` MUST declare `identity="service"` (REQ-1125), and every other fetcher this repository ships MUST keep the caller's identity.

> The boundaries are open reference data, and onboarding asks for them before the person
> is a member of anything, holding `digital-twin.values.read` and no `dataset.query`. The
> Digital Twin's own client holds `dataset.query`. Every other fetcher reads rows that
> `dataset-api` narrows to the caller, which only the caller's token can do.
