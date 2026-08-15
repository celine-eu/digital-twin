# What this repository depends on, and what depends on it

The minimum perimeter for working here. Paths are written `../<repo>`, which resolves when
this repository is checked out inside the `celine-dev` workspace and not otherwise.

**This package sits in the middle of the platform**: it turns what `../dataset-api` serves
into domain models — community, participant, grid — and four repositories build on those
models. Both directions matter, and neither is visible from inside this tree.

**Working on it alone, you cannot see your own blast radius.** No consumer's test suite
runs against this package. If a change moves a domain, a value fetcher's signature or a
route, get the `celine-dev` workspace and read the component-model entry in its
`.agents/knowledge/` — named rather than linked, because a path into the workspace does not
resolve from inside a member.

## Consumed

Everything CELINE arrives through the **`celine-sdk` package**, never by reaching into a
sibling checkout:

| Import | Owned by | For |
|---|---|---|
| `celine.sdk.rec_registry`, `celine.sdk.openapi.rec_registry.schemas` | `../rec-registry` | community and membership structure |
| `celine.sdk.nudging.client`, `celine.sdk.openapi.nudging.models` | `../nudging-tool` | notifications |
| `celine.sdk.broker` | `../celine-sdk` | MQTT event listening |
| `celine.sdk.auth`, `celine.sdk.auth.provider`, `celine.sdk.settings.models` | `../celine-sdk` | identity and shared settings |

Plus the data itself: **value fetchers query `../dataset-api`**, which serves what
`../celine-pipelines` governance declares. That is the chain a wrong number travels back
along — three repositories, none of which fails when this one returns the wrong thing.

## Consumed by

| Consumer | Uses |
|---|---|
| `../celine-grid` | `celine.sdk.dt` — grid risk data |
| `../celine-webapp` | `celine.sdk.dt`, `celine.sdk.dt.community` — the bulk of its fan-out |
| `../celine-ai-assistant` | `celine.sdk.dt` — the energy-data skill |
| `../flexibility-api` | `celine.sdk.dt` |

They reach this service **through the SDK client**, not directly. So a change to a route or
a response shape here reaches them at their next SDK regeneration or version bump — with
no file in those repositories changing, and no test of theirs running against it.

## Which seams this repository sits on

Two of the five, and it is on both sides of the first:

- **API contract** — it serves one to four consumers and consumes several. This is the seam
  that matters here, and the one with the widest blast radius in the platform after the SDK
  itself.
- **Data schema** — inbound. Value fetchers are written against the tables `dataset-api`
  exposes; a renamed gold column surfaces here as an empty or failing fetcher.

It publishes no governance metadata, maps nothing to an ontology, and makes no identity
decision of its own.

## Configuration is alive, optional and merged

Worth knowing before you go looking for a config file that "should" be read:
`domains_config_paths`, `clients_config_paths` and `brokers_config_paths` are **lists of
glob patterns**, settable from the environment. Every match is loaded, sorted and merged;
for domains the merge key is the domain `name`, so a later file *replaces* an earlier
declaration rather than adding to it.

**A pattern that matches nothing logs at debug and startup continues.** A typo is
indistinguishable from a feature nobody configured.

## Related

- `query-templates-are-two-phase.md` — the rendering rule and the `::` cast lookbehind.
- `rec-fetcher-row-limits.md`
- `app-state-is-reached-through-infra.md` — the other silent-absence trap: a defaulted
  `getattr` on `app.state` reports an empty service with a 200.
- `a-fetcher-id-is-local-in-the-path-namespaced-in-the-registry.md` — why the consumers
  all send the local id, and what breaks when a handler forgets to namespace.
- `../playbooks/extending-a-domain.md` — adding a domain, a value fetcher, custom routes,
  an event handler.
- `docs/domains.md` — the DTDomain contract and how routes are mounted.
