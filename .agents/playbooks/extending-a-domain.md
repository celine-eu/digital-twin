# Playbook — adding a domain, and adding to one

The four things done repeatedly in this repository. Each is a procedure, not a design
decision; what a domain *is* and what the runtime mounts for it is in `docs/domains.md`.

## Adding a domain

1. Create `src/celine/dt/domains/{name}/domain.py`.
2. Subclass `DTDomain` and set the identity class variables: `name`, `domain_type`,
   `version`, `route_prefix`, `entity_id_param`.
3. Override `get_value_specs()` to declare the data fetchers.
4. Optionally override `resolve_entity()` to validate the entity id from the URL and enrich
   `EntityInfo.metadata`. Anything put in metadata becomes available to every query template
   in the domain, which is the cheapest way to avoid a second round trip.
5. Create a `routes` subpackage for custom endpoints, if any.
6. Register it in `config/domains.yaml`: `name` → import path → a **module-level**
   `domain = MyDomain()` instance. The loader imports the path and looks for that name; a
   domain constructed inside a function is not found.
7. Nothing else is wired by hand — the runtime mounts `/values`, `/simulations`,
   `/ontology` and `/info` for the domain, plus whatever that subpackage exports.

The convention is a base class per domain *type* (`GridDomain`), then a locale subclass
(`ITGridDomain`). Put anything locale-independent in the base, or the second locale
duplicates it.

## Adding a value fetcher

Declare a `ValueFetcherSpec` in the domain's `get_value_specs()`:

| Field | What it is |
|---|---|
| `id` | short local name; the runtime namespaces it as `{domain.name}.{id}` |
| `client` | must match a key in `config/clients.yaml`, or startup fails |
| `query` | a Jinja2 SQL template — **read `.agents/knowledge/query-templates-are-two-phase.md` before writing one** |
| `payload_schema` | JSON Schema for the input; callers read it from `/describe` |
| `output_mapper` | shapes the result |

The knowledge entry is not optional reading. Putting a caller-supplied value in the Jinja
half rather than in a bind parameter is the mistake this spec makes easy.

## Adding custom routes

Create a module under `src/celine/dt/domains/{name}/routes/`. It is auto-discovered, and
exports:

- `router = APIRouter()` — required
- `__prefix__ = "/my-prefix"` — optional, defaults to empty
- `__tags__ = ["My Tag"]` — optional

Take the request context with `Depends(get_ctx)`, or `Depends(get_ctx_auth)` when the route
needs a JWT. Use `ctx.fetch_value("fetcher_id", payload)` rather than calling a client
directly, so the route goes through the same spec, schema validation and mapper as the
generic endpoint.

## Adding an event handler

Decorate a domain method with `@on_event`:

```python
from celine.dt.core.broker.decorators import on_event

class MyDomain(DTDomain):
    @on_event("my.event.type", topics=["celine/my/topic/+"])
    async def handle_event(self, event: DTEvent, ctx: EventContext) -> None:
        ...
```

`EventContext` carries `topic`, `broker_name`, `infra` and `entity_id`.

The decorator also works on plain module-level functions, which are discovered by
`scan_handlers()` as configured in `main.py` — use that only when the handler genuinely
belongs to no domain, because a handler outside a domain has no entity to scope itself to.

## After any of these

1. **Check there is a requirement for what you added.** `docs/specifications/` states what
   the service must do. If your change introduces behaviour nobody has specified, state it
   there first — and if stating it needs a decision nobody has taken, ask rather than
   inventing one.
2. **Write the test, and tag it** with `# @verifies REQ-####`.
   `tests/test_traceability.py` fails on a requirement nothing verifies.
3. **Run the suite.** `uv run pytest -q`. No external service is needed: the dataset client
   and the JWT check are the only things faked. Invocations and traps are in
   `.agents/playbooks/testing.md`.

Two of these tests will catch a new domain or fetcher without your writing anything:
`tests/test_domain_specs.py` loads `config/domains.yaml` for real and holds every shipped
fetcher to its invariants — importable domain, configured client, no caller data in query
structure, every `:param` declared, and the query rendering under both a minimal and a full
payload. A fetcher that fails one of those fails the suite the moment you declare it.

**Check whether the change crosses a seam.** A new route, a changed response shape or a
changed fetcher signature reaches `../celine-webapp`, `../celine-grid`,
`../celine-ai-assistant` and `../flexibility-api` at their next `celine-sdk` bump — with no
file of theirs changing and no test of theirs running against it.
`.agents/knowledge/what-this-repository-depends-on.md`.
