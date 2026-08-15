---
slug: the-suite-has-not-followed-the-code
created: 2026-08-15
status: proposed
requires-new-spec: false
---

# Plan — the test suite catches up with the code it tests

## This is a defect

It should be filed as an issue (`gh issue create`). This plan exists because the operator
asked for findings from the harness migration to land in a plan in the repository they
belong to.

## What was measured

2026-08-15, clean checkout, nothing changed:

```bash
uv run pytest -q
```

```text
ImportError: cannot import name 'build_domain_router' from 'celine.dt.api.domain_router'
ERROR tests/test_domain_routing.py
!!!! Interrupted: 1 error during collection !!!!
1 error in 0.99s
```

**Zero tests ran.** An error during collection aborts the whole session, so `task test`
completes without executing a single assertion while looking like it did something.

Excluding that one module:

```text
10 failed, 20 passed in 0.97s
```

So of roughly thirty tests, **eleven are broken** and the suite as invoked verifies
nothing at all.

## The cause is uniform: signatures moved, tests did not

Every failure is the same kind. The production code was refactored and the suite was left
where it was.

| Symptom | What changed |
|---|---|
| `cannot import name 'build_domain_router'` | the function is `build_router` — a rename |
| `ValuesFetcher.fetch() missing 1 required keyword-only argument: 'ctx'` | a context parameter was threaded through |
| `_MockClient.query() got an unexpected keyword argument 'ctx'` | the same refactor, seen from the test double's side |
| `DTDomain.resolve_entity() missing 1 required positional argument` | a required parameter was added |
| `'FetcherDescriptor' object is not subscriptable` | a dict-like structure became a typed descriptor |

None of these is a disagreement about behaviour. They are a suite that describes an
earlier version of this package.

**That is the part worth acting on.** These tests were not *failing* in a way anyone had to
look at — the collection error meant nobody saw a result at all, so eleven broken tests
accumulated without a single red run to prompt a fix.

## Shape of the fix

Mechanical, and in this order:

1. **`tests/test_domain_routing.py` first.** While it fails to import, nothing else runs
   and no progress is visible. Change the import to `build_router` and see what the module
   actually asserts.
2. **Thread `ctx` through the test doubles.** `_MockClient.query()` and the `ValuesFetcher`
   call sites in `tests/test_values.py`. The doubles need to accept what the real
   collaborators now accept.
3. **`FetcherDescriptor`.** Replace subscript access with whatever the descriptor exposes.
4. **`DTDomain.resolve_entity()`** — supply the added argument, and check whether the
   test's intent survives it or whether the added parameter changed the behaviour being
   asserted.

Step 4 is the only one that might not be mechanical. Do not assume it is: an added required
parameter sometimes means the old test was asserting something that no longer has meaning.

## Then make the rot visible next time

Nothing in this repository runs the suite automatically — there is no CI workflow for it.
A collection error is exactly the failure mode that a green-by-absence habit hides, and it
hid this one for however long the refactor has been in.

Adding CI is a second change and is not smuggled into the fix.

## Open, and for the operator

1. **Should the suite grow while it is being repaired, or only be repaired?** There are
   thirty tests for a package that four repositories depend on. Repair and expansion are
   different pieces of work and mixing them makes the repair unreviewable.
2. **Is `../celine-grid`'s suite the model to follow?** It was written in the same week
   against the same serviceless constraint and now has 247 tests with a CI trace check.
   Following it beats inventing a shape.

## Exit criterion

`uv run pytest -q` **collects cleanly** and reports 0 failed and 0 errors on a clean
checkout.

Do not close this by deleting the broken tests. Four repositories import this package;
these thirty tests are most of what stands between a refactor here and a runtime failure
there.
