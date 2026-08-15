# Playbook — testing a change

## Running the suite

```bash
uv run pytest -q                       # everything
uv run pytest -q -k "cast"             # by name
uv run pytest tests/test_template.py   # one module
task test                              # the same, through the taskfile
```

No external service is needed. Nothing here reaches `dataset-api`, a broker or an OIDC
issuer; the dataset client and the JWT check are the only things faked.

**Establish the baseline before changing anything.** A pre-existing failure attributed to
your change costs an afternoon. Note the number and the `xfail` count before you start.

> **The suite was repaired on 2026-08-15.** Before then a collection error aborted the
> session and *zero* tests ran, while `task test` still exited quickly and looked clean.
> If you find a report quoting "10 failed, 20 passed" or claiming the suite does not run,
> it predates that. The record is `.agents/plans/the-suite-has-not-followed-the-code.md`.

## What each module covers

| Module | Covers |
|---|---|
| `tests/test_template.py` | query rendering: the two phases, `::` casts, the injection boundary, filters |
| `tests/test_values.py` | the executor and the values service: validation, defaults, mappers, pagination, startup wiring |
| `tests/test_domain_registry.py` | registration, prefix collision, `match_path` |
| `tests/test_domain_routing.py` | the HTTP surface, end to end, through `TestClient` |
| `tests/test_domain_specs.py` | the domains this repository **ships**, held to their invariants |
| `tests/test_traceability.py` | every requirement has a verifying test, and every tag names a real requirement |

`tests/conftest.py` builds an app the way `create_app` does. `tests/sample_domain/` is a
domain laid out on disk as a real one is — it has to be a package, because route discovery
derives the routes package from the domain class's *module path*, so a domain declared
inline in a test file silently has no discoverable routes.

## Writing a test

**Tag what it verifies.** A comment directly above the test, or a line in its docstring:

```python
# @verifies REQ-1103
def test_fetch_value_get(self):
    ...
```

`tests/test_traceability.py` fails if a requirement in `docs/specifications/` has no tag,
or if a tag names a requirement that does not exist. The requirement universe and how to
write one is `docs/specifications/index.md`.

**A change needs a requirement before it needs a test.** If the behaviour you are adding
is not stated in `docs/specifications/`, state it there first — and if stating it requires
a decision nobody has taken, ask rather than inventing one.

## The two seams a test here cannot cross

Both are real, and neither fails in this repository when it breaks:

- **`dataset-api`.** Value fetchers are written against gold tables that no test reaches.
  A renamed column surfaces as an empty result, not an error. What the suite *can* do is
  hold every shipped query to rendering under its own schema — `test_domain_specs.py` does
  that, and it is the closest thing to coverage of the query text itself.
- **The four consumers.** `../celine-grid`, `../celine-webapp`, `../celine-ai-assistant`
  and `../flexibility-api` build on this package through `celine-sdk`. A change to a route
  or a response shape reaches them at their next SDK regeneration — with no file of theirs
  changing and no test of theirs running against it. See
  `.agents/knowledge/what-this-repository-depends-on.md`.

The broker is also unexercised: event subscription and `@on_event` dispatch have no
coverage.

## Before changing a domain or a value fetcher

Two traps, both in `.agents/knowledge/`:

- **Query templates render in two phases**, and the `::` cast lookbehind is why a naive
  substitution breaks — `query-templates-are-two-phase.md`. The casts are now pinned by
  `TestPostgresCasts`; that class is the regression guard, so read it before touching
  `BIND_PARAM_PATTERN`.
- **Configuration is globbed and merged**, and a pattern matching nothing logs at *debug*
  and lets startup continue — `what-this-repository-depends-on.md`. A typo in a config
  path looks exactly like a feature nobody configured.

Also: **the test double's signature is part of the contract.** `MockDatasetClient.query`
takes `ctx` because the real client does. The 2026-08-15 breakage was precisely this —
`ctx` was threaded through the executor and the doubles were not updated, so eleven tests
failed with a `TypeError` that reads like a test bug and is not one. When you change what
the executor passes a client, change `tests/conftest.py` in the same commit.

## Reporting

**Read the error count before the passing count.** A collection error produces no verdict
for anything, and a run that aborts during collection still exits quickly.

State what ran, what did not, and what was skipped. An `xfail` is not a pass: the suite
currently carries one, marking the `rec_self_consumption` row-limit defect, and it is
`strict=True` so it will fail the suite when the defect is fixed — which is the prompt to
close the requirement rather than to delete the marker.
