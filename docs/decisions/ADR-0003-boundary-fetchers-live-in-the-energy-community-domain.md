# ADR-0003 — The boundary fetchers live in the energy-community domain, and `source` is a closed enum

**Date:** 2026-09-27
**Status:** accepted

## Context

A renewable energy community's areas are being redefined as references to published
reference boundaries — for Italy, the GSE conventional primary-substation areas, one shape
per substation code, already loaded into the gold layer and exposed by `dataset-api` as an
open dataset. Two consumers need to ask about them:

- **onboarding**, at eligibility: which boundary contains this supply address's point? It
  asks with its own service token, before the person is a member of anything;
- **the community dashboard's backend**, for a read-only map: the shapes of this community's
  boundaries, by id.

Hence two value fetchers, `boundary_at_point(source, lat, lon)` and
`boundary_shape(source, ids)`. Every value fetcher here is reached under a domain's entity
route, so they have to live in some domain. Three were candidates:

- **`it-grid`** already serves geometry, but it models a distribution network's resilience:
  its entity is a `network_id`, and neither consumer has one. Hosting boundaries there would
  make both callers invent an entity for a question that is not about a network.
- **A new reference-geography domain** would be the purest home, and it would cost a new
  domain registration, a new route prefix, a new generated client surface in `celine-sdk` and
  new consumer wiring, for two read-only fetchers. Nothing else would live in it yet.
- **The energy-community domain** is where the question comes from: areas exist to model the
  community incentive, both consumers already address the Digital Twin by community, and the
  base class `EnergyCommunityDomain` is inherited by every locale variant.

The shapes are country-specific; the question is not. Another country's communities will want
the same two answers from their own boundary tables (a NUTS or LAU table, say), and the
extension point has to be somewhere that does not require a new fetcher per country.

## Decision

Declare both fetchers in the **base energy-community domain**, in a module the locale variants
share, so `it-energy-community` registers them today and any later locale variant inherits
them unchanged. They are reached as
`/communities/it/{community_id}/values/boundary_at_point` and `…/boundary_shape`.

**A point on a boundary's edge is inside it, and a point in more than one shape resolves to the
lowest id.** `boundary_at_point` tests that the shape *covers* the point, not that it *contains*
it, so a supply address on a line two boundaries share is never "outside every boundary"; of
several covering shapes it answers the one with the lowest `id` in lexical order, so the wizard
and the approval that re-checks it always get the same id. The requester settled both, and the
base-domain placement, on 2026-09-27 (REQ-1153, REQ-1155).

**The community in the path does not scope the answer.** A reference boundary belongs to no
community; the entity is the address the runtime needs, not a filter. Both fetchers query
`dataset-api` with the Digital Twin's own service token, not the caller's forwarded one
(`identity="service"`, REQ-1125, REQ-1160; the requester, 2026-09-28): a caller needs
`digital-twin.values.read` (the `svc-digital-twin` audience the route still requires) and no
`dataset.query`. Every other fetcher keeps forwarding the caller's token.

**`source` is a closed enum** in both fetchers' `payload_schema`, initially
`gse_cabine_primarie` alone. Each value selects one gold table through a Jinja branch written
into the template; the value itself never reaches the statement. A new country's boundaries
are a new enum value and a new branch, reviewed like any other change to a statement — not a
new fetcher, and never a table name taken from the request. An unknown value is refused at
payload validation.

The requirements are `docs/specifications/values.md` (reference boundaries) and
`docs/specifications/query-templates.md` (table selection), marked planned under ADR-0002.

## Consequences

- `dataset-api` sees the Digital Twin, not the caller, on these two statements: its audit
  and any row filter it applies name the Digital Twin's client. That is acceptable for the
  same reason as the next point, and it is what lets onboarding ask before the person is a
  member, without a `dataset-api` grant of its own.
- A caller must name some community to ask a geography question. Onboarding knows the
  community a template binds, and the dashboard asks for its own, so neither is burdened
  today; a caller with no community would be, and that is the point at which a
  reference-geography domain earns its cost.
- Because the path does not scope the answer, any authenticated caller that can reach one
  community route can read every boundary of an enabled source. That is acceptable only
  because the sources are open reference data; a source holding anything else does not belong
  in this enum.
- The enum is the whole extension surface. Loosening it to a free string, or to a table name,
  would make the request choose what the statement reads — the interpolation REQ-1210
  forbids, one level up.
- **What will tempt someone to undo it:** the second country. Its boundaries will look like
  they belong in its own locale domain. They can live there as an override if its shapes need
  different columns; while they answer the same two questions from a table of the same shape,
  one more enum value is the smaller change.
