# There is exactly one thing on `app.state`, and reaching for anything else silently works

`create_app` sets **`app.state.infra`** and nothing else. Every shared service — the values
service, the domain registry, the broker, the clients registry, the ontology service, the
token provider — hangs off that one `Infrastructure` object.

## The trap

`getattr(request.app.state, "domain_registry", None)` compiles, runs, and returns `None`.
Starlette's `State` raises `AttributeError` on a missing key, so the `getattr` default
swallows it, and the caller takes the "not configured yet" branch. On a fully loaded
service with three domains registered.

That is exactly what `GET /domains` and `GET /health` did until 2026-08-15: `/domains`
answered `200 []` and `/health` reported `"domains": 0` and `"broker": "not configured"`,
on a healthy service. **Nothing logs.** A monitor watching `/health` for a 200 sees a pass.

The shape to distrust is a defaulted `getattr` against `app.state` for anything other than
`infra`. It is indistinguishable from correct code and it is never right.

## Why it survived

`main.py` was refactored to funnel everything through `Infrastructure`, and the two
discovery routes were not part of the refactor's blast radius as anyone read it — they do
not import the registry, they only ask app state for it. Nothing failed, because failing
would have required something to raise.

## The second half of the trap

`Infrastructure.domain_registry` is a **property that raises `RuntimeError`** until
`create_app` assigns `_domain_registry`, and `subscription_manager` and `token_provider`
do the same until the lifespan finishes. So the correct read is not simply
`app.state.infra.domain_registry` — during startup that raises, and an unguarded read turns
a legitimate transient state into a 500.

Reading it correctly means both: go through `infra`, *and* catch the `RuntimeError` that
means "not loaded yet". `src/celine/dt/api/discovery.py:_domain_registry` is the reference
implementation.

## What to do with it

- Anything a route needs comes from `ctx` (via `Depends(get_ctx)`) or from
  `domain.infra`. Neither reads `app.state` directly.
- When a route genuinely must read app state — the discovery routes have no entity and so
  no `ctx` — read `app.state.infra` and handle the not-yet-loaded `RuntimeError`.
- Verified by REQ-1050 and REQ-1051 (`docs/specifications/runtime.md`), which assert the
  counts rather than the status code. Asserting `/health` returns 200 is what let this
  through: it did.

## Related

- `what-this-repository-depends-on.md` — configuration is globbed and merged, and a
  pattern matching nothing also fails silently. Same failure family: absence that reads
  as "not configured".
