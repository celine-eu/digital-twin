# Playbook — testing a change

## ⚠️ The suite does not run

Measured 2026-08-15 on a clean checkout:

```bash
uv run pytest -q
```

```text
ImportError: cannot import name 'build_domain_router' from 'celine.dt.api.domain_router'
ERROR tests/test_domain_routing.py
!!!! Interrupted: 1 error during collection !!!!
```

**Zero tests execute.** A collection error aborts the whole session, so `task test`
finishes without running a single assertion — and finishes quickly, which is part of why it
has gone unnoticed.

Excluding that module: `10 failed, 20 passed`. Eleven of about thirty tests are broken, all
because signatures moved and the tests did not follow. Recorded in
`.agents/plans/the-suite-has-not-followed-the-code.md`.

**Until that plan is closed, this repository has no working baseline.** Say so when
reporting, rather than quoting a number the suite did not produce.

## Running what does work

```bash
uv run pytest -q --ignore=tests/test_domain_routing.py   # 20 pass, 10 fail
uv run pytest tests/test_template.py -q                  # this module is clean
uv run pytest -q -k "name"
```

`task test` exists and runs `pytest` — it inherits the collection error.

## What the suite covers when it works

| Module | Covers | State |
|---|---|---|
| `tests/test_template.py` | query template rendering — the two-phase rule | clean |
| `tests/test_values.py` | value fetchers and the values service | **9 failing** |
| `tests/test_domain_registry.py` | domain registration and entity resolution | **1 failing** |
| `tests/test_domain_routing.py` | route mounting per domain | **does not import** |

## What no layer covers

- **`../dataset-api`.** Value fetchers query it and nothing here exercises that against a
  real service, so a renamed gold column surfaces as an empty result rather than an error.
- **The broker.** Event subscription and `@on_event` dispatch are not exercised.
- **The four consumers.** `../celine-grid`, `../celine-webapp`, `../celine-ai-assistant`
  and `../flexibility-api` all build on this package through `celine-sdk`. A change here
  reaches them at their next bump, with no file of theirs changing and no test of theirs
  running against it. See `what-this-repository-depends-on.md`.

## Before changing a domain or a value fetcher

Two traps, both in `.agents/knowledge/`:

- **Query templates render in two phases**, and the `::` cast lookbehind is why a naive
  substitution breaks — `query-templates-are-two-phase.md`.
- **Configuration is globbed and merged.** A pattern matching nothing logs at *debug* and
  startup continues, so a typo in a config path looks exactly like a feature nobody
  configured.

The procedure for adding a domain, a fetcher, a custom route or an event handler is
`.agents/playbooks/extending-a-domain.md`.

## Declaring what a test verifies

This repository traces no requirements — `.agents/harness.toml` names no traceability
provider and no requirement identifiers exist here. No `@verifies` tag is needed unless
that changes.

## Reporting

**Read the error count before the passing count.** A collection error produces no verdict
for anything, and that is exactly the state this repository is in — a run that looks fast
and clean while asserting nothing at all.
