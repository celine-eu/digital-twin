# A fetcher identifier is domain-local in the URL and namespaced in the registry

Two forms of the same identifier, and which one you need depends on where you are:

| Where | Form | Example |
|---|---|---|
| `ValueFetcherSpec.id`, as the domain declares it | local | `rec_self_consumption` |
| the values registry key | namespaced | `it-energy-community.rec_self_consumption` |
| the URL path | **local** | `POST /communities/it/{id}/values/rec_self_consumption` |
| `GET /values` listing, and `/describe` responses | **namespaced** | `it-energy-community.rec_self_consumption` |
| `ctx.fetch_value(...)` and `domain.fetch_values(...)` | local — they namespace for you | `rec_self_consumption` |

The runtime applies the prefix once, in `main._register_domain_values`, and the route
handlers re-apply it when they look the fetcher up.

## The trap

**The listing hands you a form the path does not take.** `GET /values` returns namespaced
ids; putting one straight back into the path yields a lookup for
`it-energy-community.it-energy-community.rec_self_consumption` and a 404. It reads like the
fetcher was deleted.

Going the other way is worse. Until 2026-08-15 `GET /values/{fetcher_id}` did **not**
namespace while `POST` and `/describe` did, so the two verbs on one path took different
identifiers — and the GET handler had no error handling at all, so the local id every
consumer sends produced an uncaught `KeyError` and a 500. It went unnoticed because
`celine-sdk` exposes only the POST form: `dt.communities.fetch_values(...)` and
`dt.participants.fetch_values(...)` both POST. Nothing in the platform called the GET
endpoint, so nothing reported it.

## Why the split exists at all

The registry is flat and process-wide — one `ValuesRegistry` for every domain — so it needs
globally unique keys. The URL already carries the domain in its prefix, so repeating it in
the path segment would be redundant and would let a caller address another domain's
fetcher from inside this domain's entity scope. The namespacing is what prevents that: the
handler builds the key from `entity.domain_name`, not from anything the caller sent.

**That is the property to preserve.** A "fix" that accepted either form would let
`/communities/it/{id}/values/it-grid.risks` resolve.

## What to do with it

- Adding a route that fetches: use `ctx.fetch_value("local_id", payload)`. It namespaces,
  validates and maps. Do not touch the registry or the client directly.
- Adding an endpoint that resolves a fetcher from a path segment: build the key as
  `f"{entity.domain_name}.{fetcher_id}"`, and answer 404 on `KeyError` — not 500, and not
  by letting it escape.
- Requirements: REQ-1100, REQ-1103 and REQ-1106 in `docs/specifications/values.md`;
  REQ-1052 in `docs/specifications/runtime.md`.

## Related

- `what-this-repository-depends-on.md` — the consumers, and why a route change here does
  not fail any test of theirs.
