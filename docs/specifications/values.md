# Specification — values

Value fetcher registration, execution, validation and pagination.

How to write a fetcher is `docs/values.md` and
`.agents/playbooks/extending-a-domain.md`. This document says only what must hold.

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

---

## Execution

### REQ-1120 — The rendered query MUST be executed through the client named by the fetcher's spec.

### REQ-1121 — The request context MUST be passed to the client with the query.

> This is what carries the caller's identity to `dataset-api`. It was threaded through the
> executor in a refactor that the test doubles did not follow — see
> `.agents/plans/the-suite-has-not-followed-the-code.md`.

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
> `.agents/knowledge/rec-fetcher-row-limits.md`. Tracked as an issue; see that entry.
